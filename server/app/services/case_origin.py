from app.models import Case


def origin_dict(case: Case) -> dict:
    return {
        "type": "github" if case.repo_url else "paste",
        "repo_url": case.repo_url,
        "commit_sha": case.commit_sha,
        "file_path": case.file_path,
    }


def origin_label(case: Case) -> str:
    if case.repo_url:
        # GitHub 링크 제출은 다음 단계 기능이라 현재는 이 분기에 도달하는 case가 없다.
        return f"{case.repo_url}@{case.commit_sha} · {case.file_path}"
    return "붙여넣기로 제출됨"
