import asyncio
from pathlib import Path

from app.fixtures.data import SAMPLE_CODE, SAMPLE_LANGUAGE
from app.services.llm_provider import FixtureLLMProvider
from app.services.rule_catalog import RuleCatalog
from app.services.worker import run_worker_once

from tests.conftest import CSRF_HEADERS, register_and_login

REPO_ROOT = Path(__file__).resolve().parents[2]


def _submit_and_sentence_to_judgment(client):
    register_and_login(client)
    submit = client.post(
        "/api/v1/cases",
        json={"code": SAMPLE_CODE, "language": SAMPLE_LANGUAGE},
        headers=CSRF_HEADERS,
    )
    case_id = submit.json()["case_id"]

    catalog = RuleCatalog.load(REPO_ROOT / "rules.yaml")
    provider = FixtureLLMProvider()
    for _ in range(3):
        assert asyncio.run(
            run_worker_once(client.session_factory, provider, catalog, "test-worker")  # type: ignore[attr-defined]
        )

    detail = client.get(f"/api/v1/cases/{case_id}").json()
    return case_id, detail["judgment"]["sentences"]


def test_toggle_sentence_updates_completed_at_and_progress(client):
    case_id, sentences = _submit_and_sentence_to_judgment(client)
    assert len(sentences) == 3
    sentence_id = sentences[0]["sentence_id"]

    response = client.patch(
        f"/api/v1/sentences/{sentence_id}", json={"completed": True}, headers=CSRF_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sentence_id"] == sentence_id
    assert body["completed_at"] is not None
    assert body["progress"] == {"done": 1, "total": 3}

    second_id = sentences[1]["sentence_id"]
    response2 = client.patch(
        f"/api/v1/sentences/{second_id}", json={"completed": True}, headers=CSRF_HEADERS
    )
    assert response2.json()["progress"] == {"done": 2, "total": 3}

    # 완료 해제 시 completed_at이 NULL로 돌아가고 이행률도 다시 줄어든다
    response3 = client.patch(
        f"/api/v1/sentences/{sentence_id}", json={"completed": False}, headers=CSRF_HEADERS
    )
    assert response3.json()["completed_at"] is None
    assert response3.json()["progress"] == {"done": 1, "total": 3}

    # 토글이 사건 상태 자체를 바꾸지 않는다
    progress = client.get(f"/api/v1/cases/{case_id}/progress")
    assert progress.json()["status"] == "SENTENCED"


def test_toggle_nonexistent_sentence_returns_404(client):
    register_and_login(client)
    response = client.patch(
        "/api/v1/sentences/00000000-0000-0000-0000-000000000099",
        json={"completed": True},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SENTENCE_NOT_FOUND"


def test_toggle_another_users_sentence_returns_404(client):
    _, sentences = _submit_and_sentence_to_judgment(client)
    sentence_id = sentences[0]["sentence_id"]

    register_and_login(client, email="other@example.com")
    response = client.patch(
        f"/api/v1/sentences/{sentence_id}", json={"completed": True}, headers=CSRF_HEADERS
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SENTENCE_NOT_FOUND"


def test_toggle_requires_csrf_header(client):
    _, sentences = _submit_and_sentence_to_judgment(client)
    sentence_id = sentences[0]["sentence_id"]
    response = client.patch(f"/api/v1/sentences/{sentence_id}", json={"completed": True})
    assert response.status_code == 403


def test_toggle_requires_login(client):
    response = client.patch(
        "/api/v1/sentences/00000000-0000-0000-0000-000000000099",
        json={"completed": True},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 401
