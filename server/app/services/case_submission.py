import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import Case, CaseStatus, GitHubFetchAttempt
from app.services.case_origin import origin_dict, origin_label
from app.services.code import MAX_CHARS, MAX_LINES, check_length, compute_code_hash
from app.services.code import total_lines as count_total_lines
from app.services.github import (
    FileTooLargeError,
    GitHubUnavailableError,
    InvalidRepoUrlError,
    RepoFileUnavailableError,
    fetch_ref,
    parse_github_blob_url,
)

ALLOWED_LANGUAGES = {"python", "javascript", "typescript", "java", "other"}
DAILY_CASE_LIMIT = 20
RATE_LIMIT_WINDOW = timedelta(hours=24)

FETCH_RATE_LIMIT = 60
FETCH_RATE_LIMIT_WINDOW = timedelta(hours=24)

_ACTIVE_STATUSES = [
    status
    for status in CaseStatus
    if status not in (CaseStatus.SENTENCED, CaseStatus.DISMISSED, CaseStatus.FAILED)
]


def _validate_submission(code: str, language: str) -> None:
    if not code.strip():
        raise ApiError(400, "EMPTY_CODE", "코드가 비어 있습니다.")
    if language not in ALLOWED_LANGUAGES:
        raise ApiError(400, "INVALID_LANGUAGE", "language 필드가 없거나 형식이 올바르지 않습니다.")
    length = check_length(code)
    if length.exceeds:
        raise ApiError(
            400,
            "CODE_TOO_LONG",
            "코드가 500줄 또는 20000자를 초과했습니다.",
            {"max_lines": MAX_LINES, "max_chars": MAX_CHARS},
        )


async def _check_rate_limit(session: AsyncSession, user_id: uuid.UUID) -> None:
    window_start = datetime.now(timezone.utc) - RATE_LIMIT_WINDOW
    count = (
        await session.execute(
            select(func.count())
            .select_from(Case)
            .where(Case.user_id == user_id, Case.created_at >= window_start)
        )
    ).scalar_one()
    if count < DAILY_CASE_LIMIT:
        return

    oldest = (
        await session.execute(
            select(func.min(Case.created_at)).where(
                Case.user_id == user_id, Case.created_at >= window_start
            )
        )
    ).scalar_one()
    if oldest.tzinfo is None:  # SQLite는 timezone-aware datetime을 보존하지 않는다
        oldest = oldest.replace(tzinfo=timezone.utc)
    retry_after = RATE_LIMIT_WINDOW - (datetime.now(timezone.utc) - oldest)
    raise ApiError(
        429,
        "RATE_LIMITED",
        "24시간 내 20건을 모두 사용했습니다.",
        {
            "limit": DAILY_CASE_LIMIT,
            "window": "24h",
            "retry_after_seconds": max(0, int(retry_after.total_seconds())),
        },
    )


async def _check_fetch_rate_limit(session: AsyncSession, user_id: uuid.UUID) -> None:
    window_start = datetime.now(timezone.utc) - FETCH_RATE_LIMIT_WINDOW
    count = (
        await session.execute(
            select(func.count())
            .select_from(GitHubFetchAttempt)
            .where(GitHubFetchAttempt.user_id == user_id, GitHubFetchAttempt.created_at >= window_start)
        )
    ).scalar_one()
    if count >= FETCH_RATE_LIMIT:
        raise ApiError(
            429,
            "FETCH_RATE_LIMITED",
            "링크 불러오기 횟수를 초과했습니다.",
            {"limit": FETCH_RATE_LIMIT, "window": "24h"},
        )


async def _record_fetch_attempt(session: AsyncSession, user_id: uuid.UUID) -> None:
    # 성공/실패와 무관하게 시도 자체를 기록한다 — 실패를 공짜로 두면 이 카운터의 존재 의미가 없어진다.
    session.add(GitHubFetchAttempt(user_id=user_id))
    await session.commit()


async def _find_cached_case(
    session: AsyncSession, user_id: uuid.UUID, code_hash: str, language: str
) -> Case | None:
    stmt = (
        select(Case)
        .where(
            Case.user_id == user_id,
            Case.code_hash == code_hash,
            Case.language == language,
            Case.status.in_([CaseStatus.SENTENCED, CaseStatus.DISMISSED]),
            Case.rejudgment_failed_at.is_(None),
        )
        .order_by(Case.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _find_in_progress_case(
    session: AsyncSession, user_id: uuid.UUID, code_hash: str, language: str
) -> Case | None:
    stmt = select(Case).where(
        Case.user_id == user_id,
        Case.code_hash == code_hash,
        Case.language == language,
        Case.status.in_(_ACTIVE_STATUSES),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _submit_common(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    code: str,
    language: str,
    force_retrial: bool,
    repo_url: str | None = None,
    commit_sha: str | None = None,
    file_path: str | None = None,
) -> tuple[int, dict]:
    _validate_submission(code, language)

    # 캐시 히트는 코드 내용(code_hash) 기준이다 — 출처(붙여넣기/GitHub, 저장소)가 달라도 동일하게 취급한다.
    code_hash = compute_code_hash(code, language)
    total_lines = count_total_lines(code)

    cached_case = await _find_cached_case(session, user_id, code_hash, language)
    if cached_case is not None and not force_retrial:
        return 200, {
            "case_id": cached_case.id,
            "cached": True,
            "origin": origin_dict(cached_case),
            "origin_label": origin_label(cached_case),
        }

    await _check_rate_limit(session, user_id)

    new_case = Case(
        user_id=user_id,
        code=code,
        language=language,
        code_hash=code_hash,
        total_lines=total_lines,
        repo_url=repo_url,
        commit_sha=commit_sha,
        file_path=file_path,
        status=CaseStatus.QUEUED_PROSECUTION,
        previous_case_id=cached_case.id if cached_case is not None else None,
    )
    session.add(new_case)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if force_retrial:
            raise ApiError(409, "RETRIAL_BLOCKED", "진행 중인 사건이 있어 재판을 새로 시작할 수 없습니다.")
        existing = await _find_in_progress_case(session, user_id, code_hash, language)
        return 200, {"case_id": existing.id, "cached": False, "in_progress": True}

    result = {"case_id": new_case.id, "cached": False}
    if cached_case is not None:
        result["previous_case_id"] = cached_case.id
    return 202, result


async def _submit_link(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    repo_url: str,
    force_retrial: bool,
    github_client: httpx.AsyncClient,
) -> tuple[int, dict]:
    try:
        ref = parse_github_blob_url(repo_url)
    except InvalidRepoUrlError as exc:
        raise ApiError(400, "INVALID_REPO_URL", "GitHub 파일(blob) 링크가 아닙니다.") from exc

    # fetch "시도" 자체에 대한 상한 — 사건 생성 카운트와 별개. 성공 여부와 무관하게 먼저 기록한다.
    await _check_fetch_rate_limit(session, user_id)
    await _record_fetch_attempt(session, user_id)

    try:
        fetched = await fetch_ref(ref, client=github_client)
    except RepoFileUnavailableError as exc:
        raise ApiError(
            400, "REPO_FILE_UNAVAILABLE", "파일을 불러올 수 없습니다. 공개 저장소인지 확인해 주세요."
        ) from exc
    except FileTooLargeError as exc:
        raise ApiError(
            400,
            "CODE_TOO_LONG",
            "코드가 500줄 또는 20000자를 초과했습니다.",
            {"max_lines": MAX_LINES, "max_chars": MAX_CHARS},
        ) from exc
    except GitHubUnavailableError as exc:
        raise ApiError(
            503, "GITHUB_UNAVAILABLE", "GitHub에서 파일을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요."
        ) from exc

    return await _submit_common(
        session,
        user_id=user_id,
        code=fetched.code,
        language=fetched.language,
        force_retrial=force_retrial,
        repo_url=f"https://github.com/{ref.owner}/{ref.repo}",
        commit_sha=fetched.commit_sha,
        file_path=ref.path,
    )


async def submit_case(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    code: str | None,
    language: str | None,
    repo_url: str | None,
    force_retrial: bool,
    github_client: httpx.AsyncClient | None = None,
) -> tuple[int, dict]:
    """POST /cases의 본 로직. (http_status, CaseSubmissionResult dict)를 반환한다.

    code+language(붙여넣기) 또는 repo_url(GitHub 링크) 중 정확히 하나만 받는다.
    """
    has_paste = code is not None or language is not None
    has_link = repo_url is not None
    if has_paste and has_link:
        raise ApiError(
            400, "VALIDATION_ERROR", "code/language와 repo_url을 동시에 보낼 수 없습니다."
        )

    if has_link:
        if github_client is None:
            raise ValueError("repo_url 제출에는 github_client가 필요합니다.")
        return await _submit_link(
            session, user_id=user_id, repo_url=repo_url, force_retrial=force_retrial, github_client=github_client
        )

    if code is None or language is None:
        raise ApiError(400, "VALIDATION_ERROR", "code와 language가 모두 필요합니다.")
    return await _submit_common(session, user_id=user_id, code=code, language=language, force_retrial=force_retrial)
