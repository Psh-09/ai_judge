import asyncio
import uuid
from pathlib import Path

from app.fixtures.data import SAMPLE_CODE, SAMPLE_LANGUAGE
from app.models import Case, CaseStatus, Charge
from app.services.llm_provider import FixtureLLMProvider
from app.services.rule_catalog import RuleCatalog
from app.services.worker import run_worker_once

from tests.conftest import CSRF_HEADERS, register_and_login

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_list_cases_returns_only_own_cases_newest_first(client):
    register_and_login(client, email="alice@example.com")
    a1 = client.post(
        "/api/v1/cases", json={"code": "a1 = 1\n", "language": "python"}, headers=CSRF_HEADERS
    ).json()["case_id"]
    a2 = client.post(
        "/api/v1/cases", json={"code": "a2 = 1\n", "language": "python"}, headers=CSRF_HEADERS
    ).json()["case_id"]
    a3 = client.post(
        "/api/v1/cases", json={"code": "a3 = 1\n", "language": "python"}, headers=CSRF_HEADERS
    ).json()["case_id"]

    register_and_login(client, email="bob@example.com")
    client.post("/api/v1/cases", json={"code": "b1 = 1\n", "language": "python"}, headers=CSRF_HEADERS)

    register_and_login(client, email="alice@example.com")
    response = client.get("/api/v1/cases")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert [item["case_id"] for item in body["items"]] == [a3, a2, a1]  # 최신순
    assert body["page"] == 1
    assert body["per_page"] == 20


def test_list_cases_pagination(client):
    register_and_login(client)
    for i in range(3):
        client.post(
            "/api/v1/cases", json={"code": f"p{i} = 1\n", "language": "python"}, headers=CSRF_HEADERS
        )

    first_page = client.get("/api/v1/cases", params={"page": 1, "per_page": 2})
    assert first_page.status_code == 200
    body1 = first_page.json()
    assert body1["total"] == 3
    assert len(body1["items"]) == 2
    assert body1["page"] == 1
    assert body1["per_page"] == 2

    second_page = client.get("/api/v1/cases", params={"page": 2, "per_page": 2})
    body2 = second_page.json()
    assert len(body2["items"]) == 1

    ids_page1 = {item["case_id"] for item in body1["items"]}
    ids_page2 = {item["case_id"] for item in body2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_list_cases_summary_fields_after_sentencing(client):
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

    body = client.get("/api/v1/cases").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["case_id"] == case_id
    assert item["status"] == "SENTENCED"
    assert item["origin_label"] == "직접 제출"
    assert item["charges_count"] == 5
    assert item["sustained_count"] == 2  # SEC-003, STRUCT-001만 SUSTAINED (ERR-002는 REDUCED)
    assert item["sentence_progress"] == {"done": 0, "total": 3}


def test_list_cases_requires_login(client):
    response = client.get("/api/v1/cases")
    assert response.status_code == 401


def test_rule_frequency_returns_top_5_ordered_by_count(client):
    user_id = uuid.UUID(register_and_login(client, email="frequent@example.com"))

    # 동률이 없도록 서로 다른 횟수를 준다 (동률이면 상위 5개 컷오프가 불확정적이 됨)
    counts = {
        "SEC-003": 6,
        "STRUCT-001": 5,
        "ERR-002": 4,
        "NAMING-002": 3,
        "STYLE-001": 2,
        "PERF-001": 1,  # 6번째 rule_id -> 상위 5개에서 제외되어야 함
    }

    async def seed():
        async with client.session_factory() as session:  # type: ignore[attr-defined]
            for rule_id, count in counts.items():
                for i in range(count):
                    case = Case(
                        user_id=user_id,
                        code=f"# {rule_id} {i}\n",
                        language="python",
                        code_hash=f"hash-{rule_id}-{i}",
                        total_lines=1,
                        status=CaseStatus.SENTENCED,
                    )
                    session.add(case)
                    await session.flush()
                    session.add(
                        Charge(
                            case_id=case.id,
                            charge_index=0,
                            raw_index=0,
                            rule_id=rule_id,
                            evidence_start=1,
                            evidence_end=1,
                            charged_severity="LOW",
                            severity_adjusted=False,
                            description="d",
                        )
                    )
            await session.commit()

    asyncio.run(seed())

    response = client.get("/api/v1/cases/rule-frequency")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 5
    assert [item["rule_id"] for item in items] == [
        "SEC-003",
        "STRUCT-001",
        "ERR-002",
        "NAMING-002",
        "STYLE-001",
    ]
    assert items[0]["count"] == 6
    assert items[0]["rule_title"] == "SQL 문자열 결합"
    assert "PERF-001" not in [item["rule_id"] for item in items]


def test_rule_frequency_requires_login(client):
    response = client.get("/api/v1/cases/rule-frequency")
    assert response.status_code == 401
