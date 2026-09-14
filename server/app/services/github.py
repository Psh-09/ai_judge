from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.services.code import MAX_CHARS, MAX_LINES

GITHUB_HOSTS = {"github.com", "www.github.com"}
FETCH_TIMEOUT_SECONDS = 10.0
STREAM_CHUNK_BYTES = 8192

# 확장자 -> 언어 매핑. 목록에 없으면 "other" (ALLOWED_LANGUAGES와 맞춘다).
EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
}


class InvalidRepoUrlError(Exception):
    """github.com blob 링크 형식이 아니거나 디렉터리(tree) 링크일 때."""


class RepoFileUnavailableError(Exception):
    """저장소/참조/파일을 찾을 수 없을 때 (비공개 저장소 포함 — 구분하지 않고 404로 취급)."""


class GitHubUnavailableError(Exception):
    """GitHub API 오류, rate limit, 타임아웃 등 서버 쪽 문제로 볼 수 있는 경우."""


class FileTooLargeError(Exception):
    """스트리밍 중 500줄/20000자 상한을 넘겨서 조기 중단했을 때."""


@dataclass(frozen=True)
class GitHubBlobRef:
    owner: str
    repo: str
    ref: str
    path: str


@dataclass(frozen=True)
class FetchedFile:
    code: str
    commit_sha: str
    language: str


def parse_github_blob_url(url: str) -> GitHubBlobRef:
    """예: https://github.com/octocat/sample-api/blob/main/src/handlers/user.py

    ref 자체에 '/'가 포함된 브랜치명(예: feature/foo)은 지원하지 않는다 — blob URL만으로는
    ref와 path의 경계가 원래 모호하며, 이 프로젝트가 다루는 예시는 전부 단순 ref이기 때문이다.
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise InvalidRepoUrlError("GitHub 파일(blob) 링크가 아닙니다.") from exc

    if (
        parsed.scheme not in ("http", "https")
        or parsed.hostname is None
        or parsed.hostname.lower() not in GITHUB_HOSTS
    ):
        raise InvalidRepoUrlError("GitHub 파일(blob) 링크가 아닙니다.")

    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 5 or segments[2] != "blob":
        raise InvalidRepoUrlError("GitHub 파일(blob) 링크가 아닙니다.")

    owner, repo, _blob, ref, *path_parts = segments
    path = "/".join(path_parts)
    if not path:
        raise InvalidRepoUrlError("GitHub 파일(blob) 링크가 아닙니다.")

    return GitHubBlobRef(owner=owner, repo=repo, ref=ref, path=path)


def infer_language(path: str) -> str:
    for ext, language in EXTENSION_LANGUAGE_MAP.items():
        if path.endswith(ext):
            return language
    return "other"


async def _resolve_commit_sha(client: httpx.AsyncClient, ref: GitHubBlobRef) -> str:
    """브랜치명이 아니라 그 시점의 커밋 SHA를 고정하기 위해 ref를 먼저 실제 커밋으로 해석한다."""
    url = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/commits/{ref.ref}"
    try:
        response = await client.get(url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise GitHubUnavailableError(str(exc)) from exc

    if response.status_code == 404:
        raise RepoFileUnavailableError("저장소 또는 참조를 찾을 수 없습니다.")
    if response.status_code != 200:
        # 3xx(따라가지 않은 리다이렉트 포함)·403/429(rate limit)·5xx를 전부 서버측 문제로 취급한다.
        raise GitHubUnavailableError(f"GitHub API 오류: {response.status_code}")

    sha = response.json().get("sha")
    if not sha:
        raise GitHubUnavailableError("GitHub 응답에 커밋 SHA가 없습니다.")
    return sha


async def _fetch_raw_content(client: httpx.AsyncClient, ref: GitHubBlobRef, commit_sha: str) -> str:
    """raw.githubusercontent.com에서 직접 바이트 스트림으로 받아, 상한 초과 시 다 받기 전에 중단한다."""
    url = f"https://raw.githubusercontent.com/{ref.owner}/{ref.repo}/{commit_sha}/{ref.path}"
    try:
        async with client.stream(
            "GET", url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False
        ) as response:
            if response.status_code == 404:
                raise RepoFileUnavailableError("파일을 찾을 수 없습니다.")
            if response.status_code != 200:
                raise GitHubUnavailableError(f"GitHub 오류: {response.status_code}")

            buffer = bytearray()
            newline_count = 0
            async for chunk in response.aiter_bytes(STREAM_CHUNK_BYTES):
                buffer.extend(chunk)
                newline_count += chunk.count(b"\n")
                if len(buffer) > MAX_CHARS or newline_count > MAX_LINES:
                    raise FileTooLargeError("파일이 500줄 또는 20000자를 초과합니다.")
    except httpx.HTTPError as exc:
        raise GitHubUnavailableError(str(exc)) from exc

    return buffer.decode("utf-8", errors="replace")


async def fetch_ref(ref: GitHubBlobRef, *, client: httpx.AsyncClient) -> FetchedFile:
    commit_sha = await _resolve_commit_sha(client, ref)
    code = await _fetch_raw_content(client, ref, commit_sha)
    return FetchedFile(code=code, commit_sha=commit_sha, language=infer_language(ref.path))
