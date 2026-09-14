from app.models import Case


def origin_dict(case: Case) -> dict:
    return {
        "type": "github" if case.repo_url else "paste",
        "repo_url": case.repo_url,
        "commit_sha": case.commit_sha,
        "file_path": case.file_path,
    }


def _owner_repo(repo_url: str) -> str:
    return "/".join(repo_url.rstrip("/").split("/")[-2:])


def origin_label(case: Case) -> str:
    """캐시 히트 안내 등에 쓰는 표기. "owner/repo@sha · path" 또는 "붙여넣기로 제출됨"."""
    if case.repo_url:
        return f"{_owner_repo(case.repo_url)}@{case.commit_sha} · {case.file_path}"
    return "붙여넣기로 제출됨"


def origin_label_short(case: Case) -> str:
    """CaseSummary(GET /cases 목록)용 축약 표기. "owner/repo" 또는 "직접 제출"."""
    if case.repo_url:
        return _owner_repo(case.repo_url)
    return "직접 제출"
