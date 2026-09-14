import asyncio
import uuid

import httpx

from app.dependencies import get_github_client
from app.main import app
from app.models import Case, CaseStatus

from tests.conftest import CSRF_HEADERS, register_and_login

SAMPLE_CONTENT = 'def add(a, b):\n    return a + b\n'
COMMIT_SHA = "abc123def456"


def _default_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "api.github.com/repos/octocat/sample-api/commits/" in url:
        return httpx.Response(200, json={"sha": COMMIT_SHA})
    if f"raw.githubusercontent.com/octocat/sample-api/{COMMIT_SHA}/src/app.py" in url:
        return httpx.Response(200, content=SAMPLE_CONTENT.encode())
    if f"raw.githubusercontent.com/octocat/sample-api/{COMMIT_SHA}/huge.py" in url:
        return httpx.Response(200, content=("x = 1\n" * 600).encode())
    if "api.github.com/repos/octocat/ghost-repo" in url:
        return httpx.Response(404)
    if f"raw.githubusercontent.com/octocat/sample-api/{COMMIT_SHA}/missing.py" in url:
        return httpx.Response(404)
    if "api.github.com/repos/octocat/down-repo" in url:
        return httpx.Response(200, json={"sha": COMMIT_SHA})
    if f"raw.githubusercontent.com/octocat/down-repo/{COMMIT_SHA}" in url:
        return httpx.Response(502)
    return httpx.Response(404)


def _override_client(handler=_default_handler):
    async def _get_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield client

    return _get_client


def _use_mock_github():
    app.dependency_overrides[get_github_client] = _override_client()


def _clear_mock_github():
    app.dependency_overrides.pop(get_github_client, None)


def test_invalid_url_format_returns_400(client):
    _use_mock_github()
    try:
        register_and_login(client)
        response = client.post(
            "/api/v1/cases",
            json={"repo_url": "not a github url"},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REPO_URL"
    finally:
        _clear_mock_github()


def test_directory_tree_link_returns_400(client):
    _use_mock_github()
    try:
        register_and_login(client)
        response = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/sample-api/tree/main/src"},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REPO_URL"
    finally:
        _clear_mock_github()


def test_missing_file_returns_400_repo_file_unavailable(client):
    _use_mock_github()
    try:
        register_and_login(client)
        response = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/sample-api/blob/main/missing.py"},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "REPO_FILE_UNAVAILABLE"
    finally:
        _clear_mock_github()


def test_nonexistent_repo_returns_400_repo_file_unavailable(client):
    _use_mock_github()
    try:
        register_and_login(client)
        response = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/ghost-repo/blob/main/x.py"},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "REPO_FILE_UNAVAILABLE"
    finally:
        _clear_mock_github()


def test_oversized_file_returns_400_code_too_long(client):
    _use_mock_github()
    try:
        register_and_login(client)
        response = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/sample-api/blob/main/huge.py"},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "CODE_TOO_LONG"
        assert body["error"]["details"]["max_lines"] == 500
    finally:
        _clear_mock_github()


def test_github_upstream_error_returns_503(client):
    _use_mock_github()
    try:
        register_and_login(client)
        response = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/down-repo/blob/main/x.py"},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "GITHUB_UNAVAILABLE"
    finally:
        _clear_mock_github()


def test_both_paste_and_link_fields_returns_400_validation_error(client):
    register_and_login(client)
    response = client.post(
        "/api/v1/cases",
        json={
            "code": "print(1)\n",
            "language": "python",
            "repo_url": "https://github.com/octocat/sample-api/blob/main/src/app.py",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_neither_paste_nor_link_returns_400_validation_error(client):
    register_and_login(client)
    response = client.post("/api/v1/cases", json={}, headers=CSRF_HEADERS)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_successful_link_submission_stores_commit_sha_and_infers_language(client):
    _use_mock_github()
    try:
        register_and_login(client)
        response = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/sample-api/blob/main/src/app.py"},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 202
        case_id = response.json()["case_id"]

        detail = client.get(f"/api/v1/cases/{case_id}").json()
        assert detail["language"] == "python"
        assert detail["origin"]["repo_url"] == "https://github.com/octocat/sample-api"
        assert detail["origin"]["commit_sha"] == COMMIT_SHA
        assert detail["origin"]["file_path"] == "src/app.py"
        assert detail["origin"]["type"] == "github"
    finally:
        _clear_mock_github()


def test_paste_and_link_submission_of_same_content_hits_cache(client):
    _use_mock_github()
    try:
        register_and_login(client)

        link_response = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/sample-api/blob/main/src/app.py"},
            headers=CSRF_HEADERS,
        )
        case_id = link_response.json()["case_id"]

        # 사건이 SENTENCED/DISMISSED가 아니면 캐시 대상이 아니므로, 직접 DISMISSED로 만들어
        # "내용이 같으면 출처가 달라도 히트한다"는 캐시 판정 자체만 검증한다.
        async def mark_dismissed():
            async with client.session_factory() as session:  # type: ignore[attr-defined]
                case = await session.get(Case, uuid.UUID(case_id))
                case.status = CaseStatus.DISMISSED
                await session.commit()

        asyncio.run(mark_dismissed())

        paste_response = client.post(
            "/api/v1/cases",
            json={"code": SAMPLE_CONTENT, "language": "python"},
            headers=CSRF_HEADERS,
        )
        assert paste_response.status_code == 200
        body = paste_response.json()
        assert body["cached"] is True
        assert body["case_id"] == case_id
        assert body["origin_label"] == f"octocat/sample-api@{COMMIT_SHA} · src/app.py"
    finally:
        _clear_mock_github()


def test_fetch_rate_limit_is_separate_from_case_creation_limit(client):
    _use_mock_github()
    try:
        register_and_login(client, email="heavy-fetch@example.com")

        # 60번은 성공(같은 파일이라 캐시로 흡수되지만, fetch 자체는 매번 시도된다)
        for _ in range(60):
            response = client.post(
                "/api/v1/cases",
                json={"repo_url": "https://github.com/octocat/sample-api/blob/main/src/app.py"},
                headers=CSRF_HEADERS,
            )
            assert response.status_code in (200, 202), response.text

        limited = client.post(
            "/api/v1/cases",
            json={"repo_url": "https://github.com/octocat/sample-api/blob/main/src/app.py"},
            headers=CSRF_HEADERS,
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "FETCH_RATE_LIMITED"

        # 사건 생성 카운트(20/24h)는 아직 하나도 안 썼으므로 붙여넣기 제출은 영향받지 않는다
        paste_response = client.post(
            "/api/v1/cases",
            json={"code": "y = 2\n", "language": "python"},
            headers=CSRF_HEADERS,
        )
        assert paste_response.status_code == 202
    finally:
        _clear_mock_github()
