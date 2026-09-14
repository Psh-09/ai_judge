import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.fixtures.data import SAMPLE_CODE, SAMPLE_CODE_HASH, SAMPLE_LANGUAGE
from app.models import (
    Case,
    CaseStatus,
    Charge,
    FailedStage,
    FailureReason,
    Judgment,
    Plea,
    Sentence,
    User,
    Verdict,
)
from app.models.base import Base
from app.services.llm_provider import FixtureLLMProvider, LLMProvider, Role
from app.services.rule_catalog import RuleCatalog
from app.services.worker import (
    pick_up_next_case,
    process_stage,
    reap_stale_locks,
    run_worker_once,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def catalog():
    return RuleCatalog.load(REPO_ROOT / "rules.yaml")


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def _seed_case(session_factory, code: str, language: str, code_hash: str, total_lines: int):
    async with session_factory() as session:
        user = User(email="worker-test@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        case = Case(
            user_id=user.id,
            code=code,
            language=language,
            code_hash=code_hash,
            total_lines=total_lines,
            status=CaseStatus.QUEUED_PROSECUTION,
        )
        session.add(case)
        await session.commit()
        return case.id


class _EmptyChargesProvider(LLMProvider):
    async def generate(self, role: Role, request: dict) -> dict:
        assert role == Role.PROSECUTION
        return {"charges": []}


class _AlwaysFailsProvider(LLMProvider):
    async def generate(self, role: Role, request: dict) -> dict:
        raise RuntimeError("provider unavailable")


class _SlowProvider(LLMProvider):
    def __init__(self, delay: float):
        self.delay = delay

    async def generate(self, role: Role, request: dict) -> dict:
        await asyncio.sleep(self.delay)
        return {"charges": []}


async def test_full_happy_path_reaches_sentenced(engine, catalog):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    total_lines = len(SAMPLE_CODE.split("\n"))
    case_id = await _seed_case(session_factory, SAMPLE_CODE, SAMPLE_LANGUAGE, SAMPLE_CODE_HASH, total_lines)
    provider = FixtureLLMProvider()
    worker_id = "worker-1"

    assert await run_worker_once(session_factory, provider, catalog, worker_id) is True
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.QUEUED_DEFENSE
        assert case.prosecution_attempts == 1
        assert case.charges_truncated is False
        charges = (
            (await session.execute(select(Charge).where(Charge.case_id == case_id).order_by(Charge.charge_index)))
            .scalars()
            .all()
        )
        assert [c.rule_id for c in charges] == [
            "SEC-003",
            "STRUCT-001",
            "ERR-002",
            "NAMING-002",
            "STYLE-001",
        ]

    assert await run_worker_once(session_factory, provider, catalog, worker_id) is True
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.QUEUED_JUDGMENT
        assert case.defense_attempts == 1
        pleas = (await session.execute(select(Plea))).scalars().all()
        assert len(pleas) == 5

    assert await run_worker_once(session_factory, provider, catalog, worker_id) is True
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.SENTENCED
        assert case.judgment_attempts == 1
        judgment = (await session.execute(select(Judgment).where(Judgment.case_id == case_id))).scalar_one()
        assert judgment.revision == 0
        verdicts = (
            (await session.execute(select(Verdict).where(Verdict.judgment_id == judgment.id))).scalars().all()
        )
        assert len(verdicts) == 5
        sentences = (
            (await session.execute(select(Sentence).where(Sentence.judgment_id == judgment.id))).scalars().all()
        )
        assert len(sentences) == 3

    assert await run_worker_once(session_factory, provider, catalog, worker_id) is False


async def test_zero_valid_charges_dismisses_case_and_skips_further_stages(engine, catalog):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, "x = 1\n", "python", "no-such-hash", 1)
    provider = _EmptyChargesProvider()

    assert await run_worker_once(session_factory, provider, catalog, "worker-1") is True
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.DISMISSED

    assert await run_worker_once(session_factory, provider, catalog, "worker-1") is False


async def test_exhausting_attempts_marks_case_failed(engine, catalog):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, "x = 1\n", "python", "no-such-hash", 1)
    provider = _AlwaysFailsProvider()

    for _ in range(MAX_ATTEMPTS := 3):
        assert await run_worker_once(session_factory, provider, catalog, "worker-1") is True

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.FAILED
        assert case.failed_stage == FailedStage.PROSECUTION
        assert case.failure_reason == FailureReason.API_ERROR
        assert case.prosecution_attempts == MAX_ATTEMPTS

    assert await run_worker_once(session_factory, provider, catalog, "worker-1") is False


async def test_retryable_failure_requeues_without_exceeding_cap(engine, catalog):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, "x = 1\n", "python", "no-such-hash", 1)
    provider = _AlwaysFailsProvider()

    assert await run_worker_once(session_factory, provider, catalog, "worker-1") is True
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.QUEUED_PROSECUTION  # 재시도 대기, 아직 FAILED 아님
        assert case.prosecution_attempts == 1


async def test_reap_stale_locks_resets_timed_out_working_case(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, "x = 1\n", "python", "h", 1)

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        case.status = CaseStatus.PROSECUTING
        case.locked_by = "dead-worker"
        case.locked_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        await session.commit()

    async with session_factory() as session:
        affected = await reap_stale_locks(session)
    assert affected == 1

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.QUEUED_PROSECUTION
        assert case.locked_at is None
        assert case.locked_by is None


async def test_reap_stale_locks_leaves_fresh_locks_untouched(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, "x = 1\n", "python", "h", 1)

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        case.status = CaseStatus.PROSECUTING
        case.locked_by = "busy-worker"
        case.locked_at = datetime.now(timezone.utc)
        await session.commit()

    async with session_factory() as session:
        affected = await reap_stale_locks(session)
    assert affected == 0

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.status == CaseStatus.PROSECUTING
        assert case.locked_by == "busy-worker"


async def test_stale_conditional_commit_is_silently_discarded(engine, catalog):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, SAMPLE_CODE, SAMPLE_LANGUAGE, SAMPLE_CODE_HASH, len(SAMPLE_CODE.split("\n")))

    picked = await pick_up_next_case(session_factory, "worker-a")
    assert picked == (case_id, CaseStatus.QUEUED_PROSECUTION)

    # 다른 워커가 이미 이 사건을 재수거했다고 가정 (예: 리퍼 타임아웃 후 다른 워커가 픽업)
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        case.locked_by = "worker-b"
        await session.commit()

    provider = FixtureLLMProvider()
    await process_stage(
        session_factory, provider, catalog, case_id, CaseStatus.QUEUED_PROSECUTION, "worker-a"
    )

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.locked_by == "worker-b"  # worker-a의 완료 시도로 덮어써지지 않음
        assert case.status == CaseStatus.PROSECUTING  # worker-a가 바꾸려던 값이 반영 안 됨
        charges = (await session.execute(select(Charge).where(Charge.case_id == case_id))).scalars().all()
        assert charges == []  # 삽입도 함께 롤백됨


async def test_heartbeat_refreshes_locked_at_while_stage_is_running(engine, catalog):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, "x = 1\n", "python", "h", 1)

    picked = await pick_up_next_case(session_factory, "worker-1")
    assert picked is not None

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        locked_at_after_pickup = case.locked_at

    provider = _SlowProvider(delay=0.3)
    task = asyncio.create_task(
        process_stage(
            session_factory,
            provider,
            catalog,
            case_id,
            CaseStatus.QUEUED_PROSECUTION,
            "worker-1",
            heartbeat_interval=0.05,
        )
    )
    await asyncio.sleep(0.15)
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        locked_at_mid_flight = case.locked_at
    await task

    assert locked_at_mid_flight > locked_at_after_pickup


class _SpyProvider(LLMProvider):
    """실제 fixture 응답은 그대로 위임하되, 각 역할에 전달된 request를 기록한다."""

    prompt_version = "fixture-v1"

    def __init__(self):
        self._base = FixtureLLMProvider()
        self.recorded_requests: dict[Role, list[dict]] = {}

    async def generate(self, role: Role, request: dict) -> dict:
        self.recorded_requests.setdefault(role, []).append(request)
        return await self._base.generate(role, request)


async def test_judgment_request_includes_precedent_summaries_and_persists_verdict_ids(engine, catalog):
    from tests.test_precedent import _make_user, _seed_precedent

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        precedent_user_id = await _make_user(session)
        _, precedent_verdict_id = await _seed_precedent(
            session, user_id=precedent_user_id, rule_id="SEC-003", language="python"
        )
        await session.commit()

    case_id = await _seed_case(session_factory, SAMPLE_CODE, SAMPLE_LANGUAGE, SAMPLE_CODE_HASH, len(SAMPLE_CODE.split("\n")))
    provider = _SpyProvider()
    for _ in range(3):  # 검사 -> 변호 -> 판사
        assert await run_worker_once(session_factory, provider, catalog, "worker-1")

    judgment_requests = provider.recorded_requests[Role.JUDGMENT]
    assert len(judgment_requests) == 1
    precedents_sent = judgment_requests[0]["precedents"]
    assert any(p["rule_id"] == "SEC-003" for p in precedents_sent)
    sec_entry = next(p for p in precedents_sent if p["rule_id"] == "SEC-003")
    assert sec_entry["verdict"] == "SUSTAINED"
    assert sec_entry["reasoning"] == "판례 사유"

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.prompt_version == "fixture-v1"
        judgment = (
            await session.execute(select(Judgment).where(Judgment.case_id == case_id))
        ).scalar_one()
        assert judgment.precedent_verdict_ids == [precedent_verdict_id]


async def test_prompt_version_recorded_even_on_retryable_failure(engine, catalog):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    case_id = await _seed_case(session_factory, "x = 1\n", "python", "no-such-hash", 1)
    provider = _AlwaysFailsProvider()
    provider.prompt_version = "fixture-v1"

    assert await run_worker_once(session_factory, provider, catalog, "worker-1") is True

    async with session_factory() as session:
        case = await session.get(Case, case_id)
        assert case.prompt_version == "fixture-v1"
