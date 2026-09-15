import asyncio

from app.fixtures.data import SAMPLE_CODE, SAMPLE_LANGUAGE
from app.services.llm_provider import FixtureLLMProvider, LLMProvider, Role
from app.services.rule_catalog import RuleCatalog
from app.services.worker import run_worker_once

from tests.conftest import CSRF_HEADERS
from tests.conftest import register_and_login as _register_and_login

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


def test_submitting_without_login_returns_401(client):
    response = client.post(
        "/api/v1/cases", json={"code": "print(1)\n", "language": "python"}, headers=CSRF_HEADERS
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_submitting_without_csrf_header_returns_403(client):
    _register_and_login(client)
    response = client.post("/api/v1/cases", json={"code": "print(1)\n", "language": "python"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_CHECK_FAILED"


def test_empty_code_is_rejected(client):
    _register_and_login(client)
    response = client.post(
        "/api/v1/cases", json={"code": "   ", "language": "python"}, headers=CSRF_HEADERS
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_CODE"


def test_invalid_language_is_rejected(client):
    _register_and_login(client)
    response = client.post(
        "/api/v1/cases", json={"code": "print(1)", "language": "cobol"}, headers=CSRF_HEADERS
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_LANGUAGE"


def test_code_too_long_is_rejected(client):
    _register_and_login(client)
    huge_code = "x = 1\n" * 501
    response = client.post(
        "/api/v1/cases", json={"code": huge_code, "language": "python"}, headers=CSRF_HEADERS
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "CODE_TOO_LONG"
    assert body["error"]["details"]["max_lines"] == 500


def test_submit_new_case_returns_202(client):
    _register_and_login(client)
    response = client.post(
        "/api/v1/cases", json={"code": "print('hello')\n", "language": "python"}, headers=CSRF_HEADERS
    )
    assert response.status_code == 202
    body = response.json()
    assert body["cached"] is False
    assert "case_id" in body


def test_submitting_same_code_while_in_progress_returns_200_in_progress(client):
    _register_and_login(client)
    payload = {"code": "print('dup')\n", "language": "python"}
    first = client.post("/api/v1/cases", json=payload, headers=CSRF_HEADERS)
    assert first.status_code == 202
    first_case_id = first.json()["case_id"]

    second = client.post("/api/v1/cases", json=payload, headers=CSRF_HEADERS)
    assert second.status_code == 200
    body = second.json()
    assert body["cached"] is False
    assert body["in_progress"] is True
    assert body["case_id"] == first_case_id


def test_force_retrial_while_in_progress_returns_409(client):
    _register_and_login(client)
    payload = {"code": "print('retrial')\n", "language": "python"}
    client.post("/api/v1/cases", json=payload, headers=CSRF_HEADERS)

    response = client.post(
        "/api/v1/cases", json={**payload, "force_retrial": True}, headers=CSRF_HEADERS
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RETRIAL_BLOCKED"


def test_get_case_progress_reflects_current_status(client):
    _register_and_login(client)
    submit = client.post(
        "/api/v1/cases", json={"code": "print(1)\n", "language": "python"}, headers=CSRF_HEADERS
    )
    case_id = submit.json()["case_id"]

    response = client.get(f"/api/v1/cases/{case_id}/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "QUEUED_PROSECUTION"
    assert body["revision"] == 0
    assert body["appeal_used"] is False


def test_get_case_not_found_returns_404(client):
    _register_and_login(client)
    response = client.get("/api/v1/cases/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_another_users_case_is_404_but_owner_sees_200(client):
    _register_and_login(client, email="alice@example.com")
    submit = client.post(
        "/api/v1/cases", json={"code": "print('alice')\n", "language": "python"}, headers=CSRF_HEADERS
    )
    case_id = submit.json()["case_id"]

    # B가 A의 사건을 조회하면 404 (403이 아님 - 존재 자체를 노출하지 않음)
    _register_and_login(client, email="bob@example.com")
    forbidden = client.get(f"/api/v1/cases/{case_id}")
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "CASE_NOT_FOUND"
    forbidden_progress = client.get(f"/api/v1/cases/{case_id}/progress")
    assert forbidden_progress.status_code == 404

    # A 본인이 조회하면 200
    _register_and_login(client, email="alice@example.com")
    ok = client.get(f"/api/v1/cases/{case_id}")
    assert ok.status_code == 200
    assert ok.json()["case_id"] == case_id


def test_full_flow_submit_poll_and_read_sentenced_judgment(client):
    _register_and_login(client)
    submit = client.post(
        "/api/v1/cases",
        json={"code": SAMPLE_CODE, "language": SAMPLE_LANGUAGE},
        headers=CSRF_HEADERS,
    )
    assert submit.status_code == 202
    case_id = submit.json()["case_id"]

    catalog = RuleCatalog.load(REPO_ROOT / "rules.yaml")
    provider = FixtureLLMProvider()

    for _ in range(3):  # 검사 -> 변호 -> 판사, 한 번에 스테이지 하나씩
        worked = asyncio.run(
            run_worker_once(client.session_factory, provider, catalog, "test-worker")  # type: ignore[attr-defined]
        )
        assert worked is True

    progress = client.get(f"/api/v1/cases/{case_id}/progress")
    assert progress.json()["status"] == "SENTENCED"

    detail = client.get(f"/api/v1/cases/{case_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "SENTENCED"
    assert len(body["charges"]) == 5
    assert len(body["pleas"]) == 5
    assert body["judgment"] is not None
    assert len(body["judgment"]["verdicts"]) == 5
    assert len(body["judgment"]["sentences"]) == 3
    assert body["charges"][0]["rule_id"] == "SEC-003"
    assert body["charges"][0]["rule_title"] == "SQL 문자열 결합"
    assert body["code"] == SAMPLE_CODE


def test_cache_hit_after_dismissed_case(client):
    _register_and_login(client)

    class _EmptyChargesProvider(LLMProvider):
        async def generate(self, role: Role, request: dict) -> dict:
            return {"charges": []}

    submit = client.post(
        "/api/v1/cases", json={"code": "x = 1\n", "language": "python"}, headers=CSRF_HEADERS
    )
    case_id = submit.json()["case_id"]

    catalog = RuleCatalog.load(REPO_ROOT / "rules.yaml")
    provider = _EmptyChargesProvider()
    asyncio.run(
        run_worker_once(client.session_factory, provider, catalog, "test-worker")  # type: ignore[attr-defined]
    )

    progress = client.get(f"/api/v1/cases/{case_id}/progress")
    assert progress.json()["status"] == "DISMISSED"

    resubmit = client.post(
        "/api/v1/cases", json={"code": "x = 1\n", "language": "python"}, headers=CSRF_HEADERS
    )
    assert resubmit.status_code == 200
    body = resubmit.json()
    assert body["cached"] is True
    assert body["case_id"] == case_id
    assert body["origin_label"] == "붙여넣기로 제출됨"


def test_daily_rate_limit_is_per_user(client):
    _register_and_login(client, email="heavy@example.com")
    for i in range(20):
        response = client.post(
            "/api/v1/cases", json={"code": f"x{i} = 1\n", "language": "python"}, headers=CSRF_HEADERS
        )
        assert response.status_code == 202, response.text

    limited = client.post(
        "/api/v1/cases", json={"code": "x = 999\n", "language": "python"}, headers=CSRF_HEADERS
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"

    # 다른 사용자는 영향받지 않는다 (사용자별 슬라이딩 윈도우)
    _register_and_login(client, email="fresh@example.com")
    other = client.post(
        "/api/v1/cases", json={"code": "x = 1\n", "language": "python"}, headers=CSRF_HEADERS
    )
    assert other.status_code == 202
