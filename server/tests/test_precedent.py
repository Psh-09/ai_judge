import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Case, CaseStatus, Charge, Judgment, User, Verdict
from app.models.base import Base
from app.schemas.rule import Severity
from app.services.precedent import (
    MAX_PRECEDENTS_PER_CASE,
    MAX_PRECEDENTS_PER_CHARGE,
    fetch_precedents,
)
from app.services.validation import ValidatedCharge


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


def make_charge(rule_id="SEC-003", charge_index=0, severity=Severity.HIGH):
    return ValidatedCharge(
        charge_index=charge_index,
        raw_index=charge_index,
        rule_id=rule_id,
        evidence_start=1,
        evidence_end=1,
        charged_severity=severity,
        severity_adjusted=False,
        severity_reason=None,
        description="d",
    )


async def _seed_precedent(
    session,
    *,
    user_id,
    rule_id: str,
    language: str = "python",
    status: CaseStatus = CaseStatus.SENTENCED,
    is_overturned: bool = False,
    verdict: str = "SUSTAINED",
    reasoning: str = "판례 사유",
    created_at: datetime | None = None,
    evidence: tuple[int, int] = (10, 12),
    code: str = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10\nline11\nline12\n",
) -> tuple[uuid.UUID, int]:
    case = Case(
        user_id=user_id,
        code=code,
        language=language,
        code_hash=f"hash-{uuid.uuid4()}",
        total_lines=len(code.split("\n")),
        status=status,
    )
    session.add(case)
    await session.flush()

    charge = Charge(
        case_id=case.id,
        charge_index=0,
        raw_index=0,
        rule_id=rule_id,
        evidence_start=evidence[0],
        evidence_end=evidence[1],
        charged_severity=Severity.HIGH,
        severity_adjusted=False,
        description="d",
    )
    session.add(charge)
    await session.flush()

    judgment = Judgment(
        case_id=case.id,
        revision=0,
        opinion="op",
        is_overturned=is_overturned,
        precedent_verdict_ids=[],
        **({"created_at": created_at} if created_at else {}),
    )
    session.add(judgment)
    await session.flush()

    v = Verdict(
        judgment_id=judgment.id, charge_id=charge.id, verdict=verdict, final_severity="HIGH", reasoning=reasoning
    )
    session.add(v)
    await session.flush()

    if created_at is not None:
        case.created_at = created_at
        await session.flush()

    return case.id, v.id


async def _make_user(session) -> uuid.UUID:
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x")
    session.add(user)
    await session.flush()
    return user.id


async def test_precedent_with_matching_rule_id_is_found(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        _, verdict_id = await _seed_precedent(session, user_id=user_id, rule_id="SEC-003")
        await session.commit()

        current_case_id = uuid.uuid4()
        result = await fetch_precedents(
            session, case_id=current_case_id, language="python", charges=[make_charge(rule_id="SEC-003")]
        )
        assert result.verdict_ids == [verdict_id]
        assert result.entries[0].rule_id == "SEC-003"
        assert result.entries[0].code_snippet == "line10\nline11\nline12"


async def test_overturned_judgment_is_excluded(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        await _seed_precedent(session, user_id=user_id, rule_id="SEC-003", is_overturned=True)
        await session.commit()

        result = await fetch_precedents(
            session, case_id=uuid.uuid4(), language="python", charges=[make_charge(rule_id="SEC-003")]
        )
        assert result.entries == []


async def test_own_case_is_excluded(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        case_id, _ = await _seed_precedent(session, user_id=user_id, rule_id="SEC-003")
        await session.commit()

        result = await fetch_precedents(
            session, case_id=case_id, language="python", charges=[make_charge(rule_id="SEC-003")]
        )
        assert result.entries == []


async def test_non_sentenced_case_is_excluded(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        await _seed_precedent(session, user_id=user_id, rule_id="SEC-003", status=CaseStatus.DISMISSED)
        await session.commit()

        result = await fetch_precedents(
            session, case_id=uuid.uuid4(), language="python", charges=[make_charge(rule_id="SEC-003")]
        )
        assert result.entries == []


async def test_per_charge_cap_is_three(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        for i in range(5):
            await _seed_precedent(
                session,
                user_id=user_id,
                rule_id="SEC-003",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
        await session.commit()

        result = await fetch_precedents(
            session, case_id=uuid.uuid4(), language="python", charges=[make_charge(rule_id="SEC-003")]
        )
        assert len(result.entries) == MAX_PRECEDENTS_PER_CHARGE == 3


async def test_total_case_cap_is_ten_across_charges(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        rule_ids = ["SEC-003", "STRUCT-001", "ERR-002", "NAMING-002"]
        for rule_id in rule_ids:
            for i in range(4):  # 4곳 rule_id x 4건 = 16건 존재 (기소당 상한 3 x 4 = 12로도 넘침)
                await _seed_precedent(session, user_id=user_id, rule_id=rule_id)
        await session.commit()

        charges = [
            make_charge(rule_id="SEC-003", charge_index=0, severity=Severity.HIGH),
            make_charge(rule_id="STRUCT-001", charge_index=1, severity=Severity.HIGH),
            make_charge(rule_id="ERR-002", charge_index=2, severity=Severity.HIGH),
            make_charge(rule_id="NAMING-002", charge_index=3, severity=Severity.HIGH),
        ]
        result = await fetch_precedents(session, case_id=uuid.uuid4(), language="python", charges=charges)
        assert len(result.entries) == MAX_PRECEDENTS_PER_CASE == 10


async def test_severity_high_charges_are_filled_before_low(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        # rule_id별로 정확히 3건씩 있어야, "상위 3건" 자체가 아니라 "어느 rule_id부터 채우는지"만 검증됨
        for rule_id in ["LOW-RULE", "HIGH-RULE"]:
            for _ in range(3):
                await _seed_precedent(session, user_id=user_id, rule_id=rule_id)
        await session.commit()

        # 전체 상한을 3으로 좁혀서, HIGH 기소(먼저 채워짐) 것만 반환되게 만든다
        import app.services.precedent as precedent_module

        original_cap = precedent_module.MAX_PRECEDENTS_PER_CASE
        precedent_module.MAX_PRECEDENTS_PER_CASE = 3
        try:
            charges = [
                make_charge(rule_id="LOW-RULE", charge_index=0, severity=Severity.LOW),
                make_charge(rule_id="HIGH-RULE", charge_index=1, severity=Severity.HIGH),
            ]
            result = await fetch_precedents(
                session, case_id=uuid.uuid4(), language="python", charges=charges
            )
        finally:
            precedent_module.MAX_PRECEDENTS_PER_CASE = original_cap

        assert len(result.entries) == 3
        assert all(entry.rule_id == "HIGH-RULE" for entry in result.entries)


async def test_same_language_is_prioritized_over_newer_other_language(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user_id = await _make_user(session)
        now = datetime.now(timezone.utc)
        # 다른 언어인데 더 최신인 판례
        await _seed_precedent(
            session,
            user_id=user_id,
            rule_id="SEC-003",
            language="javascript",
            created_at=now,
        )
        # 같은 언어인데 더 오래된 판례
        _, same_language_verdict_id = await _seed_precedent(
            session,
            user_id=user_id,
            rule_id="SEC-003",
            language="python",
            created_at=now - timedelta(days=1),
        )
        await session.commit()

        result = await fetch_precedents(
            session, case_id=uuid.uuid4(), language="python", charges=[make_charge(rule_id="SEC-003")]
        )
        assert result.verdict_ids[0] == same_language_verdict_id
