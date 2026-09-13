import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import Case, CaseStatus, User
from app.services.case_origin import origin_dict, origin_label
from app.services.code import MAX_CHARS, MAX_LINES, check_length, compute_code_hash
from app.services.code import total_lines as count_total_lines

# TODO(auth): 로그인/JWT가 생기기 전까지 모든 사건을 이 고정 사용자 소유로 처리한다.
TEMP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

ALLOWED_LANGUAGES = {"python", "javascript", "typescript", "java", "other"}
DAILY_CASE_LIMIT = 20
RATE_LIMIT_WINDOW = timedelta(hours=24)

_ACTIVE_STATUSES = [
    status
    for status in CaseStatus
    if status not in (CaseStatus.SENTENCED, CaseStatus.DISMISSED, CaseStatus.FAILED)
]


async def _ensure_temp_user(session: AsyncSession) -> None:
    existing = await session.get(User, TEMP_USER_ID)
    if existing is None:
        session.add(User(id=TEMP_USER_ID, email="demo@codecourt.local", password_hash="!disabled!"))
        await session.flush()


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


async def _find_cached_case(session: AsyncSession, code_hash: str, language: str) -> Case | None:
    stmt = (
        select(Case)
        .where(
            Case.user_id == TEMP_USER_ID,
            Case.code_hash == code_hash,
            Case.language == language,
            Case.status.in_([CaseStatus.SENTENCED, CaseStatus.DISMISSED]),
        )
        .order_by(Case.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _find_in_progress_case(session: AsyncSession, code_hash: str, language: str) -> Case | None:
    stmt = select(Case).where(
        Case.user_id == TEMP_USER_ID,
        Case.code_hash == code_hash,
        Case.language == language,
        Case.status.in_(_ACTIVE_STATUSES),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def submit_case(session: AsyncSession, *, code: str, language: str, force_retrial: bool) -> tuple[int, dict]:
    """POST /cases의 본 로직. (http_status, CaseSubmissionResult dict)를 반환한다."""
    _validate_submission(code, language)
    await _ensure_temp_user(session)

    code_hash = compute_code_hash(code, language)
    total_lines = count_total_lines(code)

    cached_case = await _find_cached_case(session, code_hash, language)
    if cached_case is not None and not force_retrial:
        return 200, {
            "case_id": cached_case.id,
            "cached": True,
            "origin": origin_dict(cached_case),
            "origin_label": origin_label(cached_case),
        }

    await _check_rate_limit(session, TEMP_USER_ID)

    new_case = Case(
        user_id=TEMP_USER_ID,
        code=code,
        language=language,
        code_hash=code_hash,
        total_lines=total_lines,
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
        existing = await _find_in_progress_case(session, code_hash, language)
        return 200, {"case_id": existing.id, "cached": False, "in_progress": True}

    result = {"case_id": new_case.id, "cached": False}
    if cached_case is not None:
        result["previous_case_id"] = cached_case.id
    return 202, result
