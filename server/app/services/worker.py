import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import (
    Appeal,
    Case,
    CaseStatus,
    Charge,
    FailedStage,
    FailureReason,
    Judgment,
    Plea,
    Sentence,
    Verdict,
)
from app.services.llm_provider import LLMProvider, Role
from app.services.rule_catalog import RuleCatalog
from app.services.validation import (
    DefenseResult,
    DefenseSchemaError,
    JudgmentResult,
    JudgmentSchemaError,
    ProsecutionResult,
    ProsecutionSchemaError,
    ValidatedCharge,
    validate_defense,
    validate_judgment,
    validate_prosecution,
)

logger = logging.getLogger(__name__)

MAX_STAGE_ATTEMPTS = 3
LOCK_TIMEOUT_MINUTES = 15
DEFAULT_HEARTBEAT_SECONDS = 60.0

# QUEUED_* -> (작업중 상태, 시도 횟수 컬럼명)
STAGE_PICKUP_MAP = {
    CaseStatus.QUEUED_PROSECUTION: (CaseStatus.PROSECUTING, "prosecution_attempts"),
    CaseStatus.QUEUED_DEFENSE: (CaseStatus.DEFENDING, "defense_attempts"),
    CaseStatus.QUEUED_JUDGMENT: (CaseStatus.JUDGING, "judgment_attempts"),
    CaseStatus.QUEUED_REJUDGMENT: (CaseStatus.REJUDGING, "rejudgment_attempts"),
}

# 작업중 상태 -> 크래시 시 되돌릴 QUEUED_* 상태
STAGE_REAP_MAP = {
    CaseStatus.PROSECUTING: CaseStatus.QUEUED_PROSECUTION,
    CaseStatus.DEFENDING: CaseStatus.QUEUED_DEFENSE,
    CaseStatus.JUDGING: CaseStatus.QUEUED_JUDGMENT,
    CaseStatus.REJUDGING: CaseStatus.QUEUED_REJUDGMENT,
}

STAGE_FAILED_STAGE_MAP = {
    CaseStatus.PROSECUTING: FailedStage.PROSECUTION,
    CaseStatus.DEFENDING: FailedStage.DEFENSE,
    CaseStatus.JUDGING: FailedStage.JUDGMENT,
}


@dataclass
class StageOutcome:
    success: bool
    failure_reason: FailureReason | None = None
    detail: str = ""
    prosecution_result: ProsecutionResult | None = None
    defense_result: DefenseResult | None = None
    judgment_result: JudgmentResult | None = None


class _StaleCommit(Exception):
    """다른 워커가 이미 이 스테이지를 완료/재수거했을 때 (조건부 커밋 0행)."""


async def reap_stale_locks(session) -> int:
    """locked_at이 타임아웃을 넘긴 작업중 사건을 QUEUED_*로 되돌린다. attempts는 건드리지 않는다."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TIMEOUT_MINUTES)
    affected = 0
    for working_status, queued_status in STAGE_REAP_MAP.items():
        result = await session.execute(
            update(Case)
            .where(Case.status == working_status, Case.locked_at < threshold)
            .values(status=queued_status, locked_at=None, locked_by=None)
        )
        affected += result.rowcount
    await session.commit()
    return affected


async def pick_up_next_case(session_factory, worker_id: str):
    """SELECT ... FOR UPDATE SKIP LOCKED로 사건 하나를 집어 작업중 상태로 전이시키고 즉시 커밋한다."""
    async with session_factory() as session:
        async with session.begin():
            stmt = (
                select(Case)
                .where(Case.status.in_(list(STAGE_PICKUP_MAP)))
                .order_by(Case.updated_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            case = (await session.execute(stmt)).scalar_one_or_none()
            if case is None:
                return None

            queued_status = case.status
            working_status, attempts_field = STAGE_PICKUP_MAP[queued_status]
            setattr(case, attempts_field, getattr(case, attempts_field) + 1)
            case.status = working_status
            case.locked_at = datetime.now(timezone.utc)
            case.locked_by = worker_id
            case_id = case.id

        return case_id, queued_status


@contextlib.asynccontextmanager
async def heartbeat(session_factory, case_id, worker_id: str, interval_seconds: float):
    """스테이지 처리 중 locked_at을 주기 갱신해 다른 워커의 리퍼가 살아있는 작업을 재수거하지 않게 한다."""

    async def beat():
        while True:
            await asyncio.sleep(interval_seconds)
            async with session_factory() as session:
                await session.execute(
                    update(Case)
                    .where(Case.id == case_id, Case.locked_by == worker_id)
                    .values(locked_at=datetime.now(timezone.utc))
                )
                await session.commit()

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _load_validated_charges(session, case_id) -> list[ValidatedCharge]:
    rows = (
        (
            await session.execute(
                select(Charge).where(Charge.case_id == case_id).order_by(Charge.charge_index)
            )
        )
        .scalars()
        .all()
    )
    return [
        ValidatedCharge(
            charge_index=row.charge_index,
            raw_index=row.raw_index,
            rule_id=row.rule_id,
            evidence_start=row.evidence_start,
            evidence_end=row.evidence_end,
            charged_severity=row.charged_severity,
            severity_adjusted=row.severity_adjusted,
            severity_reason=row.severity_reason,
            description=row.description,
        )
        for row in rows
    ]


async def _load_charge_rows(session, case_id) -> dict[int, Charge]:
    rows = (await session.execute(select(Charge).where(Charge.case_id == case_id))).scalars().all()
    return {row.charge_index: row for row in rows}


async def _run_prosecution(session_factory, provider: LLMProvider, catalog: RuleCatalog, case_id) -> StageOutcome:
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        code_hash, code, language, total_lines, attempt = (
            case.code_hash,
            case.code,
            case.language,
            case.total_lines,
            case.prosecution_attempts,
        )

    request = {
        "code_hash": code_hash,
        "code": code,
        "language": language,
        "total_lines": total_lines,
        "attempt": attempt,
    }
    try:
        raw = await provider.generate(Role.PROSECUTION, request)
    except Exception as exc:  # noqa: BLE001 - provider 오류는 종류에 관계없이 재시도 대상
        return StageOutcome(success=False, failure_reason=FailureReason.API_ERROR, detail=str(exc))

    try:
        result = validate_prosecution(
            raw.get("charges"), catalog=catalog, language=language, total_lines=total_lines
        )
    except ProsecutionSchemaError as exc:
        return StageOutcome(success=False, failure_reason=FailureReason.SCHEMA_INVALID, detail=str(exc))

    return StageOutcome(success=True, prosecution_result=result)


async def _run_defense(session_factory, provider: LLMProvider, case_id) -> StageOutcome:
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        charges = await _load_validated_charges(session, case_id)
        code_hash, code, language = case.code_hash, case.code, case.language

    request = {
        "code_hash": code_hash,
        "code": code,
        "language": language,
        "charges": [
            {"charge_index": c.charge_index, "rule_id": c.rule_id, "description": c.description}
            for c in charges
        ],
    }
    try:
        raw = await provider.generate(Role.DEFENSE, request)
    except Exception as exc:  # noqa: BLE001
        return StageOutcome(success=False, failure_reason=FailureReason.API_ERROR, detail=str(exc))

    try:
        result = validate_defense(raw.get("pleas"), charge_count=len(charges))
    except DefenseSchemaError as exc:
        return StageOutcome(success=False, failure_reason=FailureReason.SCHEMA_INVALID, detail=str(exc))

    if result.needs_retry:
        return StageOutcome(
            success=False,
            failure_reason=FailureReason.SCHEMA_INVALID,
            detail="all pleas resolved to NO_RESPONSE",
        )

    return StageOutcome(success=True, defense_result=result)


async def _run_judgment(session_factory, provider: LLMProvider, catalog: RuleCatalog, case_id) -> StageOutcome:
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        charges = await _load_validated_charges(session, case_id)
        code_hash, code, language, total_lines = (
            case.code_hash,
            case.code,
            case.language,
            case.total_lines,
        )

    request = {"code_hash": code_hash, "code": code, "language": language}
    try:
        raw = await provider.generate(Role.JUDGMENT, request)
    except Exception as exc:  # noqa: BLE001
        return StageOutcome(success=False, failure_reason=FailureReason.API_ERROR, detail=str(exc))

    try:
        result = validate_judgment(
            raw, charges=charges, catalog=catalog, total_lines=total_lines, is_rejudgment=False
        )
    except JudgmentSchemaError as exc:
        return StageOutcome(success=False, failure_reason=FailureReason.SCHEMA_INVALID, detail=str(exc))

    if result.needs_retry:
        return StageOutcome(
            success=False,
            failure_reason=FailureReason.SCHEMA_INVALID,
            detail=f"missing verdicts for charge_index {result.missing_charge_indices}",
        )

    return StageOutcome(success=True, judgment_result=result)


async def _run_rejudgment(session_factory, provider: LLMProvider, catalog: RuleCatalog, case_id) -> StageOutcome:
    async with session_factory() as session:
        case = await session.get(Case, case_id)
        charges = await _load_validated_charges(session, case_id)
        code_hash, code, language, total_lines = (
            case.code_hash,
            case.code,
            case.language,
            case.total_lines,
        )
        appeal = (await session.execute(select(Appeal).where(Appeal.case_id == case_id))).scalar_one_or_none()
        rebuttal = appeal.rebuttal if appeal is not None else None

    # 항소 사유가 재심 프롬프트에 반드시 실려야 한다 — 이게 빠지면 항소 사유를 필수로 받은 이유가 사라진다.
    request = {"code_hash": code_hash, "code": code, "language": language, "rebuttal": rebuttal}
    try:
        raw = await provider.generate(Role.REJUDGMENT, request)
    except Exception as exc:  # noqa: BLE001
        return StageOutcome(success=False, failure_reason=FailureReason.API_ERROR, detail=str(exc))

    try:
        result = validate_judgment(
            raw, charges=charges, catalog=catalog, total_lines=total_lines, is_rejudgment=True
        )
    except JudgmentSchemaError as exc:
        return StageOutcome(success=False, failure_reason=FailureReason.SCHEMA_INVALID, detail=str(exc))

    if result.needs_retry:
        return StageOutcome(
            success=False,
            failure_reason=FailureReason.SCHEMA_INVALID,
            detail=(
                f"missing verdicts/rebuttal_accepted; missing_charge_indices={result.missing_charge_indices}"
            ),
        )

    return StageOutcome(success=True, judgment_result=result)


async def _conditional_complete(session, case_id, working_status, worker_id: str, values: dict) -> bool:
    stmt = (
        update(Case)
        .where(Case.id == case_id, Case.locked_by == worker_id, Case.status == working_status)
        .values(**values)
    )
    result = await session.execute(stmt)
    return result.rowcount == 1


async def process_stage(
    session_factory,
    provider: LLMProvider,
    catalog: RuleCatalog,
    case_id,
    queued_status: CaseStatus,
    worker_id: str,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_SECONDS,
) -> None:
    working_status, attempts_field = STAGE_PICKUP_MAP[queued_status]

    async with heartbeat(session_factory, case_id, worker_id, heartbeat_interval):
        if queued_status == CaseStatus.QUEUED_PROSECUTION:
            outcome = await _run_prosecution(session_factory, provider, catalog, case_id)
        elif queued_status == CaseStatus.QUEUED_DEFENSE:
            outcome = await _run_defense(session_factory, provider, case_id)
        elif queued_status == CaseStatus.QUEUED_JUDGMENT:
            outcome = await _run_judgment(session_factory, provider, catalog, case_id)
        else:  # QUEUED_REJUDGMENT
            outcome = await _run_rejudgment(session_factory, provider, catalog, case_id)

    try:
        async with session_factory() as session:
            async with session.begin():
                case = await session.get(Case, case_id)
                if case is None:
                    raise _StaleCommit()
                attempts = getattr(case, attempts_field)

                if not outcome.success:
                    logger.warning(
                        "stage failed: case_id=%s stage=%s attempt=%d/%d reason=%s detail=%s",
                        case_id,
                        queued_status.value,
                        attempts,
                        MAX_STAGE_ATTEMPTS,
                        outcome.failure_reason.value if outcome.failure_reason else None,
                        outcome.detail,
                    )

                values: dict = {"locked_at": None, "locked_by": None}

                if outcome.success:
                    if queued_status == CaseStatus.QUEUED_PROSECUTION:
                        result = outcome.prosecution_result
                        values["charges_truncated"] = result.charges_truncated
                        if result.charges:
                            values["status"] = CaseStatus.QUEUED_DEFENSE
                            for charge in result.charges:
                                session.add(
                                    Charge(
                                        case_id=case_id,
                                        charge_index=charge.charge_index,
                                        raw_index=charge.raw_index,
                                        rule_id=charge.rule_id,
                                        evidence_start=charge.evidence_start,
                                        evidence_end=charge.evidence_end,
                                        charged_severity=charge.charged_severity,
                                        severity_adjusted=charge.severity_adjusted,
                                        severity_reason=charge.severity_reason,
                                        description=charge.description,
                                    )
                                )
                        else:
                            values["status"] = CaseStatus.DISMISSED

                    elif queued_status == CaseStatus.QUEUED_DEFENSE:
                        values["status"] = CaseStatus.QUEUED_JUDGMENT
                        charge_rows = await _load_charge_rows(session, case_id)
                        for plea in outcome.defense_result.pleas:
                            session.add(
                                Plea(
                                    charge_id=charge_rows[plea.charge_index].id,
                                    plea=plea.plea,
                                    argument=plea.argument,
                                )
                            )

                    elif queued_status == CaseStatus.QUEUED_JUDGMENT:
                        values["status"] = CaseStatus.SENTENCED
                        charge_rows = await _load_charge_rows(session, case_id)
                        judgment_result = outcome.judgment_result

                        judgment = Judgment(
                            case_id=case_id,
                            revision=0,
                            opinion=judgment_result.opinion,
                            rebuttal_accepted=judgment_result.rebuttal_accepted,
                            is_overturned=False,
                            precedent_verdict_ids=[],
                        )
                        session.add(judgment)
                        await session.flush()  # judgment.id 확보

                        for verdict in judgment_result.verdicts:
                            session.add(
                                Verdict(
                                    judgment_id=judgment.id,
                                    charge_id=charge_rows[verdict.charge_index].id,
                                    verdict=verdict.verdict,
                                    final_severity=verdict.final_severity,
                                    reasoning=verdict.reasoning,
                                )
                            )
                        for sentence in judgment_result.sentences:
                            session.add(
                                Sentence(
                                    judgment_id=judgment.id,
                                    charge_id=charge_rows[sentence.charge_index].id,
                                    task=sentence.task,
                                    target_start=sentence.target_start,
                                    target_end=sentence.target_end,
                                    effort=sentence.effort,
                                    effort_adjusted=sentence.effort_adjusted,
                                    effort_reason=sentence.effort_reason,
                                    effort_clamped=sentence.effort_clamped,
                                    advisory=sentence.advisory,
                                    rationale=sentence.rationale,
                                )
                            )

                    else:  # QUEUED_REJUDGMENT
                        values["status"] = CaseStatus.SENTENCED
                        values["revision"] = 1
                        charge_rows = await _load_charge_rows(session, case_id)
                        judgment_result = outcome.judgment_result

                        new_judgment = Judgment(
                            case_id=case_id,
                            revision=1,
                            opinion=judgment_result.opinion,
                            rebuttal_accepted=judgment_result.rebuttal_accepted,
                            is_overturned=False,
                            precedent_verdict_ids=[],
                        )
                        session.add(new_judgment)
                        await session.flush()  # new_judgment.id 확보

                        for verdict in judgment_result.verdicts:
                            session.add(
                                Verdict(
                                    judgment_id=new_judgment.id,
                                    charge_id=charge_rows[verdict.charge_index].id,
                                    verdict=verdict.verdict,
                                    final_severity=verdict.final_severity,
                                    reasoning=verdict.reasoning,
                                )
                            )
                        for sentence in judgment_result.sentences:
                            session.add(
                                Sentence(
                                    judgment_id=new_judgment.id,
                                    charge_id=charge_rows[sentence.charge_index].id,
                                    task=sentence.task,
                                    target_start=sentence.target_start,
                                    target_end=sentence.target_end,
                                    effort=sentence.effort,
                                    effort_adjusted=sentence.effort_adjusted,
                                    effort_reason=sentence.effort_reason,
                                    effort_clamped=sentence.effort_clamped,
                                    advisory=sentence.advisory,
                                    rationale=sentence.rationale,
                                )
                            )

                        # 판례 처리 (plan.md §7): 원심(revision=0)과 판정이 하나라도 달라지면
                        # 원심 judgment를 is_overturned=true로 전환한다. 전부 같으면 그대로 둔다.
                        original_judgment = (
                            await session.execute(
                                select(Judgment).where(
                                    Judgment.case_id == case_id, Judgment.revision == 0
                                )
                            )
                        ).scalar_one()
                        original_verdicts = (
                            await session.execute(
                                select(Verdict).where(Verdict.judgment_id == original_judgment.id)
                            )
                        ).scalars().all()
                        original_verdict_by_charge = {v.charge_id: v.verdict for v in original_verdicts}
                        changed = any(
                            original_verdict_by_charge.get(charge_rows[v.charge_index].id) != v.verdict
                            for v in judgment_result.verdicts
                        )
                        if changed:
                            original_judgment.is_overturned = True

                elif attempts >= MAX_STAGE_ATTEMPTS:
                    if queued_status == CaseStatus.QUEUED_REJUDGMENT:
                        # 재심 실패는 FAILED가 아니라 원심 그대로 유지 (plan.md §4)
                        values["status"] = CaseStatus.SENTENCED
                        values["rejudgment_failed_at"] = datetime.now(timezone.utc)
                        values["rejudgment_failed_reason"] = (
                            outcome.detail or (outcome.failure_reason.value if outcome.failure_reason else "unknown")
                        )
                    else:
                        values["status"] = CaseStatus.FAILED
                        values["failed_stage"] = STAGE_FAILED_STAGE_MAP[working_status]
                        values["failure_reason"] = outcome.failure_reason
                else:
                    values["status"] = queued_status  # 재시도 대기열로 복귀

                updated = await _conditional_complete(session, case_id, working_status, worker_id, values)
                if not updated:
                    raise _StaleCommit()
    except _StaleCommit:
        pass  # 다른 워커가 이미 처리/재수거함 - 조용히 버림


async def run_worker_once(
    session_factory,
    provider: LLMProvider,
    catalog: RuleCatalog,
    worker_id: str,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_SECONDS,
) -> bool:
    """리퍼 실행 후 사건 하나를 집어 한 스테이지만큼 처리한다. 처리한 사건이 있으면 True."""
    async with session_factory() as session:
        await reap_stale_locks(session)

    picked = await pick_up_next_case(session_factory, worker_id)
    if picked is None:
        return False

    case_id, queued_status = picked
    await process_stage(session_factory, provider, catalog, case_id, queued_status, worker_id, heartbeat_interval)
    return True
