import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select

from app.fixtures.data import SAMPLE_CODE, SAMPLE_LANGUAGE
from app.models import Case, Judgment, Verdict
from app.services.llm_provider import FixtureLLMProvider, LLMProvider, Role
from app.services.rule_catalog import RuleCatalog
from app.services.worker import run_worker_once

from tests.conftest import CSRF_HEADERS, register_and_login

REPO_ROOT = Path(__file__).resolve().parents[2]
VALID_REBUTTAL = "이 함수는 단일 진입점 스크립트에서만 호출되므로 전역 변수 사용이 의도된 설계입니다."

# 원심(_JUDGMENT_RESPONSE)과 정확히 동일한 판정 — "판정이 전부 같으면 is_overturned 유지" 검증용.
_SAME_VERDICTS_REJUDGMENT_RESPONSE = {
    "opinion": "항소 사유를 검토했으나 원심 판단을 그대로 유지한다.",
    "rebuttal_accepted": False,
    "verdicts": [
        {"charge_index": 0, "verdict": "SUSTAINED", "final_severity": "HIGH", "reasoning": "원심과 동일."},
        {"charge_index": 1, "verdict": "SUSTAINED", "final_severity": "MEDIUM", "reasoning": "원심과 동일."},
        {"charge_index": 2, "verdict": "REDUCED", "final_severity": "MEDIUM", "reasoning": "원심과 동일."},
        {"charge_index": 3, "verdict": "DISMISSED", "final_severity": None, "reasoning": "원심과 동일."},
        {"charge_index": 4, "verdict": "DISMISSED", "final_severity": None, "reasoning": "원심과 동일."},
    ],
    "sentences": [
        {
            "charge_index": 0,
            "task": "42번 줄 쿼리를 파라미터 바인딩으로 교체",
            "target_lines": [42, 42],
            "effort": "SMALL",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "동일.",
        },
        {
            "charge_index": 1,
            "task": "parse_and_save()를 파싱·검증·저장 세 함수로 분리",
            "target_lines": [88, 140],
            "effort": "LARGE",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "동일.",
        },
        {
            "charge_index": 2,
            "task": "except 절을 예상 예외 타입으로 좁힘",
            "target_lines": [155, 158],
            "effort": "MEDIUM",
            "effort_adjusted": False,
            "effort_reason": None,
            "rationale": "동일.",
        },
    ],
}


class _RejudgmentOverride(LLMProvider):
    """rejudgment 응답만 교체하고 나머지 단계는 실제 fixture를 그대로 쓰는 테스트용 provider."""

    def __init__(self, rejudgment_response=None, rejudgment_error: Exception | None = None):
        self._base = FixtureLLMProvider()
        self._rejudgment_response = rejudgment_response
        self._rejudgment_error = rejudgment_error
        self.recorded_requests: list[dict] = []

    async def generate(self, role: Role, request: dict) -> dict:
        if role == Role.REJUDGMENT:
            self.recorded_requests.append(request)
            if self._rejudgment_error is not None:
                raise self._rejudgment_error
            return self._rejudgment_response
        return await self._base.generate(role, request)


def _catalog():
    return RuleCatalog.load(REPO_ROOT / "rules.yaml")


def _submit_and_sentence(client):
    register_and_login(client)
    submit = client.post(
        "/api/v1/cases",
        json={"code": SAMPLE_CODE, "language": SAMPLE_LANGUAGE},
        headers=CSRF_HEADERS,
    )
    case_id = submit.json()["case_id"]
    catalog = _catalog()
    provider = FixtureLLMProvider()
    for _ in range(3):
        assert asyncio.run(
            run_worker_once(client.session_factory, provider, catalog, "test-worker")  # type: ignore[attr-defined]
        )
    return case_id


def _run_rejudgment_once(client, provider):
    catalog = _catalog()
    return asyncio.run(
        run_worker_once(client.session_factory, provider, catalog, "test-worker")  # type: ignore[attr-defined]
    )


def test_appeal_requires_login(client):
    response = client.post(
        "/api/v1/cases/00000000-0000-0000-0000-000000000099/appeal",
        json={"rebuttal": VALID_REBUTTAL},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 401


def test_appeal_requires_csrf_header(client):
    case_id = _submit_and_sentence(client)
    response = client.post(f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL})
    assert response.status_code == 403


def test_appeal_on_nonexistent_case_returns_404(client):
    register_and_login(client)
    response = client.post(
        "/api/v1/cases/00000000-0000-0000-0000-000000000099/appeal",
        json={"rebuttal": VALID_REBUTTAL},
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_appeal_on_other_users_case_returns_404(client):
    case_id = _submit_and_sentence(client)
    register_and_login(client, email="other@example.com")
    response = client.post(
        f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_appeal_rebuttal_too_short_returns_400(client):
    case_id = _submit_and_sentence(client)
    response = client.post(
        f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": "너무 짧음"}, headers=CSRF_HEADERS
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REBUTTAL_TOO_SHORT"


def test_appeal_on_non_sentenced_case_returns_409(client):
    register_and_login(client)
    submit = client.post(
        "/api/v1/cases", json={"code": "x = 1\n", "language": "python"}, headers=CSRF_HEADERS
    )
    case_id = submit.json()["case_id"]  # 아직 QUEUED_PROSECUTION
    response = client.post(
        f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "APPEAL_ALREADY_USED"


def test_appeal_success_queues_rejudgment(client):
    case_id = _submit_and_sentence(client)
    response = client.post(
        f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED_REJUDGMENT"
    assert body["revision"] == 0
    assert body["appeal_used"] is True


def test_second_appeal_attempt_returns_409(client):
    case_id = _submit_and_sentence(client)
    client.post(f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS)

    second = client.post(
        f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "APPEAL_ALREADY_USED"


def test_rejudgment_success_overturns_original_and_bumps_revision(client):
    case_id = _submit_and_sentence(client)
    client.post(f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS)

    provider = FixtureLLMProvider()
    assert _run_rejudgment_once(client, provider) is True

    detail = client.get(f"/api/v1/cases/{case_id}").json()
    assert detail["status"] == "SENTENCED"
    assert detail["revision"] == 1
    assert detail["appeal_used"] is True
    assert detail["appeal"]["rebuttal"] == VALID_REBUTTAL
    # charge_index 3 (NAMING-002)가 기각 -> 채택으로 뒤집힌다
    verdict_3 = next(v for v in detail["judgment"]["verdicts"] if v["charge_index"] == 3)
    assert verdict_3["verdict"] == "SUSTAINED"
    assert detail["judgment"]["rebuttal_accepted"] is True

    async def check_original_overturned():
        async with client.session_factory() as session:  # type: ignore[attr-defined]
            original = (
                await session.execute(
                    select(Judgment).where(
                        Judgment.case_id == uuid.UUID(case_id), Judgment.revision == 0
                    )
                )
            ).scalar_one()
            assert original.is_overturned is True

    asyncio.run(check_original_overturned())


def test_rejudgment_identical_verdicts_keeps_is_overturned_false(client):
    case_id = _submit_and_sentence(client)
    client.post(f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS)

    provider = _RejudgmentOverride(rejudgment_response=_SAME_VERDICTS_REJUDGMENT_RESPONSE)
    assert _run_rejudgment_once(client, provider) is True

    detail = client.get(f"/api/v1/cases/{case_id}").json()
    assert detail["revision"] == 1  # 재심 자체는 성공(판사가 재판단은 했음)

    async def check_original_not_overturned():
        async with client.session_factory() as session:  # type: ignore[attr-defined]
            original = (
                await session.execute(
                    select(Judgment).where(
                        Judgment.case_id == uuid.UUID(case_id), Judgment.revision == 0
                    )
                )
            ).scalar_one()
            assert original.is_overturned is False

    asyncio.run(check_original_not_overturned())


def test_rejudgment_failure_keeps_original_judgment_and_appeal_used(client):
    case_id = _submit_and_sentence(client)
    client.post(f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS)

    provider = _RejudgmentOverride(rejudgment_error=RuntimeError("provider unavailable"))
    for _ in range(3):
        assert _run_rejudgment_once(client, provider) is True

    detail = client.get(f"/api/v1/cases/{case_id}").json()
    assert detail["status"] == "SENTENCED"
    assert detail["revision"] == 0  # 원심 유지
    assert detail["appeal_used"] is True  # 재항소 불가
    assert len(detail["judgment"]["verdicts"]) == 5  # 원심 판결이 그대로 유효
    assert detail["rejudgment_failed_reason"]  # API 응답에도 사유가 노출돼야 화면에 표시 가능

    async def check_failure_recorded():
        async with client.session_factory() as session:  # type: ignore[attr-defined]
            case = await session.get(Case, uuid.UUID(case_id))
            assert case.rejudgment_failed_at is not None
            assert case.rejudgment_failed_reason is not None
            assert case.rejudgment_attempts == 3

    asyncio.run(check_failure_recorded())

    # 재항소 시도는 여전히 409
    reappeal = client.post(
        f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": VALID_REBUTTAL}, headers=CSRF_HEADERS
    )
    assert reappeal.status_code == 409


def test_rejudgment_failed_case_is_not_returned_as_cache_hit(client):
    register_and_login(client)
    code = "print('unique-for-cache-test')\n"
    submit = client.post("/api/v1/cases", json={"code": code, "language": "python"}, headers=CSRF_HEADERS)
    case_id = submit.json()["case_id"]

    # 전체 재심 실패 흐름은 다른 테스트가 이미 검증했으므로, 여기서는
    # "rejudgment_failed_at이 있는 SENTENCED 사건은 캐시 대상이 아니다"만 확인하기 위해
    # 그 상태를 직접 만든다.
    async def mark_rejudgment_failed():
        from datetime import datetime, timezone

        from app.models import CaseStatus

        async with client.session_factory() as session:  # type: ignore[attr-defined]
            case = await session.get(Case, uuid.UUID(case_id))
            case.status = CaseStatus.SENTENCED
            case.rejudgment_failed_at = datetime.now(timezone.utc)
            case.rejudgment_failed_reason = "test"
            await session.commit()

    asyncio.run(mark_rejudgment_failed())

    resubmit = client.post("/api/v1/cases", json={"code": code, "language": "python"}, headers=CSRF_HEADERS)
    assert resubmit.status_code == 202  # 캐시 히트(200)가 아니라 새 사건이어야 한다
    assert resubmit.json()["case_id"] != case_id


def test_rejudgment_request_includes_the_actual_rebuttal_text(client):
    case_id = _submit_and_sentence(client)
    rebuttal = "이것은 재심 입력 전달 테스트를 위한 스무 글자 이상의 항소 사유 문장입니다."
    client.post(f"/api/v1/cases/{case_id}/appeal", json={"rebuttal": rebuttal}, headers=CSRF_HEADERS)

    provider = _RejudgmentOverride(rejudgment_response=_SAME_VERDICTS_REJUDGMENT_RESPONSE)
    assert _run_rejudgment_once(client, provider) is True

    assert len(provider.recorded_requests) == 1
    assert provider.recorded_requests[0]["rebuttal"] == rebuttal
    assert "precedents" in provider.recorded_requests[0]  # 판례 조회 결과(비어있어도 키는 실림)
