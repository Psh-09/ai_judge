import httpx
import pytest

from app.services.github import (
    FileTooLargeError,
    GitHubUnavailableError,
    InvalidRepoUrlError,
    RepoFileUnavailableError,
    fetch_ref,
    infer_language,
    parse_github_blob_url,
)


def test_parse_valid_blob_url():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/main/src/handlers/user.py")
    assert ref.owner == "octocat"
    assert ref.repo == "sample-api"
    assert ref.ref == "main"
    assert ref.path == "src/handlers/user.py"


def test_parse_valid_blob_url_with_commit_sha_ref():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/a1b2c3d/src/handlers/user.py")
    assert ref.ref == "a1b2c3d"


@pytest.mark.parametrize(
    "url",
    [
        "https://gitlab.com/octocat/sample-api/blob/main/user.py",  # 다른 호스트
        "https://github.com/octocat/sample-api/tree/main/src",  # 디렉터리(tree) 링크
        "https://github.com/octocat/sample-api",  # blob 자체가 없음
        "https://github.com/octocat/sample-api/blob/main",  # ref만 있고 path 없음
        "not a url at all",
        "ftp://github.com/octocat/sample-api/blob/main/user.py",  # 지원 안 하는 스킴
    ],
)
def test_invalid_urls_are_rejected(url):
    with pytest.raises(InvalidRepoUrlError):
        parse_github_blob_url(url)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/app.py", "python"),
        ("src/app.js", "javascript"),
        ("src/app.jsx", "javascript"),
        ("src/app.ts", "typescript"),
        ("src/app.tsx", "typescript"),
        ("src/App.java", "java"),
        ("src/app.rb", "other"),
        ("README", "other"),
    ],
)
def test_infer_language(path, expected):
    assert infer_language(path) == expected


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_fetch_ref_success_resolves_commit_and_streams_content():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/main/src/app.py")

    def handler(request: httpx.Request) -> httpx.Response:
        if "api.github.com/repos/octocat/sample-api/commits/main" in str(request.url):
            return httpx.Response(200, json={"sha": "abc123"})
        if "raw.githubusercontent.com/octocat/sample-api/abc123/src/app.py" in str(request.url):
            return httpx.Response(200, content=b"print(1)\n")
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        fetched = await fetch_ref(ref, client=client)

    assert fetched.commit_sha == "abc123"
    assert fetched.code == "print(1)\n"
    assert fetched.language == "python"


async def test_fetch_ref_commit_not_found_raises_repo_file_unavailable():
    ref = parse_github_blob_url("https://github.com/octocat/ghost-repo/blob/main/x.py")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        with pytest.raises(RepoFileUnavailableError):
            await fetch_ref(ref, client=client)


async def test_fetch_ref_file_not_found_at_commit_raises_repo_file_unavailable():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/main/missing.py")

    def handler(request: httpx.Request) -> httpx.Response:
        if "commits" in str(request.url):
            return httpx.Response(200, json={"sha": "abc123"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        with pytest.raises(RepoFileUnavailableError):
            await fetch_ref(ref, client=client)


async def test_fetch_ref_rate_limited_raises_github_unavailable():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/main/x.py")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "rate limited"})

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        with pytest.raises(GitHubUnavailableError):
            await fetch_ref(ref, client=client)


async def test_fetch_ref_oversized_file_is_aborted_during_streaming():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/main/huge.py")
    huge_content = ("x = 1\n" * 600).encode()  # 600줄 > 500줄 상한

    def handler(request: httpx.Request) -> httpx.Response:
        if "commits" in str(request.url):
            return httpx.Response(200, json={"sha": "abc123"})
        return httpx.Response(200, content=huge_content)

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        with pytest.raises(FileTooLargeError):
            await fetch_ref(ref, client=client)


async def test_fetch_ref_timeout_raises_github_unavailable():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/main/x.py")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        with pytest.raises(GitHubUnavailableError):
            await fetch_ref(ref, client=client)


async def test_fetch_ref_does_not_follow_redirects():
    ref = parse_github_blob_url("https://github.com/octocat/sample-api/blob/main/x.py")

    def handler(request: httpx.Request) -> httpx.Response:
        # 리다이렉트를 그대로 반환한다 - client가 따라가지 않으면 그대로 GitHubUnavailableError가 돼야 한다
        return httpx.Response(302, headers={"location": "https://evil.example.com/payload"})

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        with pytest.raises(GitHubUnavailableError):
            await fetch_ref(ref, client=client)
