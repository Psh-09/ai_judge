import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.fixtures.data import SAMPLE_CODE, SAMPLE_LANGUAGE
from app.main import app
from app.models.base import Base
from app.services.llm_provider import FixtureLLMProvider
from app.services.rule_catalog import RuleCatalog
from app.services.worker import run_worker_once


@pytest.fixture
def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    asyncio.run(_create_tables(engine))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        test_client.session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def test_empty_code_is_rejected(client):
    response = client.post("/api/v1/cases", json={"code": "   ", "language": "python"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_CODE"


def test_invalid_language_is_rejected(client):
    response = client.post("/api/v1/cases", json={"code": "print(1)", "language": "cobol"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_LANGUAGE"


def test_code_too_long_is_rejected(client):
    huge_code = "x = 1\n" * 501
    response = client.post("/api/v1/cases", json={"code": huge_code, "language": "python"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "CODE_TOO_LONG"
    assert body["error"]["details"]["max_lines"] == 500


def test_submit_new_case_returns_202(client):
    response = client.post(
        "/api/v1/cases", json={"code": "print('hello')\n", "language": "python"}
    )
    assert response.status_code == 202
    body = response.json()
    assert body["cached"] is False
    assert "case_id" in body


def test_submitting_same_code_while_in_progress_returns_200_in_progress(client):
    payload = {"code": "print('dup')\n", "language": "python"}
    first = client.post("/api/v1/cases", json=payload)
    assert first.status_code == 202
    first_case_id = first.json()["case_id"]

    second = client.post("/api/v1/cases", json=payload)
    assert second.status_code == 200
    body = second.json()
    assert body["cached"] is False
    assert body["in_progress"] is True
    assert body["case_id"] == first_case_id


def test_force_retrial_while_in_progress_returns_409(client):
    payload = {"code": "print('retrial')\n", "language": "python"}
    client.post("/api/v1/cases", json=payload)

    response = client.post("/api/v1/cases", json={**payload, "force_retrial": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RETRIAL_BLOCKED"


def test_get_case_progress_reflects_current_status(client):
    submit = client.post("/api/v1/cases", json={"code": "print(1)\n", "language": "python"})
    case_id = submit.json()["case_id"]

    response = client.get(f"/api/v1/cases/{case_id}/progress")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "QUEUED_PROSECUTION"
    assert body["revision"] == 0
    assert body["appeal_used"] is False


def test_get_case_not_found_returns_404(client):
    response = client.get("/api/v1/cases/00000000-0000-0000-0000-000000000099")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_full_flow_submit_poll_and_read_sentenced_judgment(client):
    submit = client.post(
        "/api/v1/cases", json={"code": SAMPLE_CODE, "language": SAMPLE_LANGUAGE}
    )
    assert submit.status_code == 202
    case_id = submit.json()["case_id"]

    catalog = RuleCatalog.load(
        __import__("pathlib").Path(__file__).resolve().parents[2] / "rules.yaml"
    )
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


def test_cache_hit_after_dismissed_case(client):
    # 유효 기소 0건 -> DISMISSED 되는 코드로 캐시 히트 흐름을 검증한다.
    from app.services.llm_provider import LLMProvider, Role

    class _EmptyChargesProvider(LLMProvider):
        async def generate(self, role: Role, request: dict) -> dict:
            return {"charges": []}

    submit = client.post("/api/v1/cases", json={"code": "x = 1\n", "language": "python"})
    case_id = submit.json()["case_id"]

    catalog = RuleCatalog.load(
        __import__("pathlib").Path(__file__).resolve().parents[2] / "rules.yaml"
    )
    provider = _EmptyChargesProvider()
    asyncio.run(
        run_worker_once(client.session_factory, provider, catalog, "test-worker")  # type: ignore[attr-defined]
    )

    progress = client.get(f"/api/v1/cases/{case_id}/progress")
    assert progress.json()["status"] == "DISMISSED"

    resubmit = client.post("/api/v1/cases", json={"code": "x = 1\n", "language": "python"})
    assert resubmit.status_code == 200
    body = resubmit.json()
    assert body["cached"] is True
    assert body["case_id"] == case_id
    assert body["origin_label"] == "붙여넣기로 제출됨"
