import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Case, CaseStatus, Charge, User
from app.models.base import Base
from app.schemas.rule import Severity

EXPECTED_TABLES = {
    "users",
    "cases",
    "charges",
    "pleas",
    "judgments",
    "verdicts",
    "sentences",
    "appeals",
}


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def test_all_tables_are_created(engine):
    async with engine.connect() as conn:
        rows = await conn.execute(text("select name from sqlite_master where type='table'"))
        names = {row[0] for row in rows}
    assert EXPECTED_TABLES <= names


async def test_insert_and_query_case_with_charge(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user = User(email="a@example.com", password_hash="x")
        session.add(user)
        await session.flush()

        case = Case(
            user_id=user.id,
            code="print(1)",
            language="python",
            code_hash="abc",
            total_lines=1,
            status=CaseStatus.QUEUED_PROSECUTION,
        )
        session.add(case)
        await session.flush()

        charge = Charge(
            case_id=case.id,
            charge_index=0,
            raw_index=0,
            rule_id="SEC-001",
            evidence_start=1,
            evidence_end=1,
            charged_severity=Severity.HIGH,
            severity_adjusted=False,
            description="d",
        )
        session.add(charge)
        await session.commit()
        case_id = case.id

    async with session_factory() as session:
        result = await session.execute(select(Case).where(Case.id == case_id))
        loaded = result.scalar_one()
        assert loaded.language == "python"
        assert loaded.status == CaseStatus.QUEUED_PROSECUTION


async def test_duplicate_charge_index_for_same_case_is_rejected(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user = User(email="b@example.com", password_hash="x")
        session.add(user)
        await session.flush()

        case = Case(
            user_id=user.id,
            code="print(1)",
            language="python",
            code_hash="def",
            total_lines=1,
            status=CaseStatus.QUEUED_PROSECUTION,
        )
        session.add(case)
        await session.flush()

        session.add_all(
            [
                Charge(
                    case_id=case.id,
                    charge_index=0,
                    raw_index=0,
                    rule_id="SEC-001",
                    evidence_start=1,
                    evidence_end=1,
                    charged_severity=Severity.HIGH,
                    severity_adjusted=False,
                    description="d",
                ),
                Charge(
                    case_id=case.id,
                    charge_index=0,
                    raw_index=1,
                    rule_id="SEC-002",
                    evidence_start=2,
                    evidence_end=2,
                    charged_severity=Severity.HIGH,
                    severity_adjusted=False,
                    description="d",
                ),
            ]
        )
        with pytest.raises(Exception):
            await session.commit()
