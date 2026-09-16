import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appeal, Case, CaseStatus, Charge, Judgment, Plea, Sentence, Verdict, VerdictValue
from app.services.case_origin import origin_dict, origin_label_short
from app.services.rule_catalog import RuleCatalog


def case_progress_dict(case: Case) -> dict:
    return {"status": case.status, "revision": case.revision, "appeal_used": case.appeal_used}


async def build_case_detail(session: AsyncSession, catalog: RuleCatalog, case: Case) -> dict:
    charges = (
        (
            await session.execute(
                select(Charge).where(Charge.case_id == case.id).order_by(Charge.charge_index)
            )
        )
        .scalars()
        .all()
    )
    charge_id_to_index = {charge.id: charge.charge_index for charge in charges}

    charge_dicts = []
    for charge in charges:
        rule = catalog.get(charge.rule_id)
        charge_dicts.append(
            {
                "charge_index": charge.charge_index,
                "rule_id": charge.rule_id,
                "rule_title": rule.title if rule is not None else charge.rule_id,
                "evidence_start": charge.evidence_start,
                "evidence_end": charge.evidence_end,
                "charged_severity": charge.charged_severity,
                "severity_adjusted": charge.severity_adjusted,
                "severity_reason": charge.severity_reason,
                "description": charge.description,
            }
        )

    plea_dicts = []
    if charges:
        pleas = (
            (
                await session.execute(
                    select(Plea).where(Plea.charge_id.in_(charge_id_to_index))
                )
            )
            .scalars()
            .all()
        )
        plea_dicts = sorted(
            (
                {
                    "charge_index": charge_id_to_index[plea.charge_id],
                    "plea": plea.plea,
                    "argument": plea.argument,
                }
                for plea in pleas
            ),
            key=lambda p: p["charge_index"],
        )

    judgment_dict = None
    if case.status == CaseStatus.SENTENCED:
        judgment_row = (
            await session.execute(
                select(Judgment).where(
                    Judgment.case_id == case.id, Judgment.revision == case.revision
                )
            )
        ).scalar_one_or_none()
        if judgment_row is not None:
            verdicts = (
                (
                    await session.execute(
                        select(Verdict).where(Verdict.judgment_id == judgment_row.id)
                    )
                )
                .scalars()
                .all()
            )
            sentences = (
                (
                    await session.execute(
                        select(Sentence).where(Sentence.judgment_id == judgment_row.id)
                    )
                )
                .scalars()
                .all()
            )
            judgment_dict = {
                "revision": judgment_row.revision,
                "opinion": judgment_row.opinion,
                "rebuttal_accepted": judgment_row.rebuttal_accepted,
                "precedent_verdict_ids": judgment_row.precedent_verdict_ids,
                "verdicts": sorted(
                    (
                        {
                            "charge_index": charge_id_to_index[v.charge_id],
                            "verdict": v.verdict,
                            "final_severity": v.final_severity,
                            "reasoning": v.reasoning,
                        }
                        for v in verdicts
                    ),
                    key=lambda v: v["charge_index"],
                ),
                "sentences": sorted(
                    (
                        {
                            "sentence_id": s.id,
                            "charge_index": charge_id_to_index[s.charge_id],
                            "task": s.task,
                            "target_start": s.target_start,
                            "target_end": s.target_end,
                            "effort": s.effort,
                            "effort_adjusted": s.effort_adjusted,
                            "effort_reason": s.effort_reason,
                            "effort_clamped": s.effort_clamped,
                            "advisory": s.advisory,
                            "rationale": s.rationale,
                            "completed_at": s.completed_at,
                        }
                        for s in sentences
                    ),
                    key=lambda s: s["charge_index"],
                ),
            }

    appeal_row = (
        await session.execute(select(Appeal).where(Appeal.case_id == case.id))
    ).scalar_one_or_none()
    appeal_dict = (
        {"rebuttal": appeal_row.rebuttal, "created_at": appeal_row.created_at}
        if appeal_row is not None
        else None
    )

    return {
        "case_id": case.id,
        "language": case.language,
        "code": case.code,
        "status": case.status,
        "revision": case.revision,
        "appeal_used": case.appeal_used,
        "charges_truncated": case.charges_truncated,
        "total_lines": case.total_lines,
        "failed_stage": case.failed_stage,
        "failure_reason": case.failure_reason,
        "rejudgment_failed_reason": case.rejudgment_failed_reason,
        "origin": origin_dict(case),
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "charges": charge_dicts,
        "pleas": plea_dicts,
        "judgment": judgment_dict,
        "appeal": appeal_dict,
    }


async def list_cases(session: AsyncSession, user_id: uuid.UUID, page: int, per_page: int) -> dict:
    total = (
        await session.execute(select(func.count()).select_from(Case).where(Case.user_id == user_id))
    ).scalar_one()

    cases = (
        (
            await session.execute(
                select(Case)
                .where(Case.user_id == user_id)
                .order_by(Case.created_at.desc())
                .limit(per_page)
                .offset((page - 1) * per_page)
            )
        )
        .scalars()
        .all()
    )

    case_ids = [case.id for case in cases]
    charges_count: dict[uuid.UUID, int] = {}
    sustained_count: dict[uuid.UUID, int] = {}
    sentence_total: dict[uuid.UUID, int] = {}
    sentence_done: dict[uuid.UUID, int] = {}

    if case_ids:
        charges_count = dict(
            (
                await session.execute(
                    select(Charge.case_id, func.count())
                    .where(Charge.case_id.in_(case_ids))
                    .group_by(Charge.case_id)
                )
            ).all()
        )
        # 재심(revision=1)이 생기면 같은 charge에 verdict/sentence가 두 벌 쌓이므로,
        # 사건의 "현재" revision과 일치하는 judgment의 것만 집계해야 이중 집계를 피한다.
        sustained_count = dict(
            (
                await session.execute(
                    select(Charge.case_id, func.count())
                    .select_from(Verdict)
                    .join(Judgment, Verdict.judgment_id == Judgment.id)
                    .join(Charge, Verdict.charge_id == Charge.id)
                    .join(Case, Judgment.case_id == Case.id)
                    .where(
                        Charge.case_id.in_(case_ids),
                        Verdict.verdict == VerdictValue.SUSTAINED,
                        Judgment.revision == Case.revision,
                    )
                    .group_by(Charge.case_id)
                )
            ).all()
        )
        sentence_total = dict(
            (
                await session.execute(
                    select(Charge.case_id, func.count())
                    .select_from(Sentence)
                    .join(Judgment, Sentence.judgment_id == Judgment.id)
                    .join(Charge, Sentence.charge_id == Charge.id)
                    .join(Case, Judgment.case_id == Case.id)
                    .where(Charge.case_id.in_(case_ids), Judgment.revision == Case.revision)
                    .group_by(Charge.case_id)
                )
            ).all()
        )
        sentence_done = dict(
            (
                await session.execute(
                    select(Charge.case_id, func.count())
                    .select_from(Sentence)
                    .join(Judgment, Sentence.judgment_id == Judgment.id)
                    .join(Charge, Sentence.charge_id == Charge.id)
                    .join(Case, Judgment.case_id == Case.id)
                    .where(
                        Charge.case_id.in_(case_ids),
                        Judgment.revision == Case.revision,
                        Sentence.completed_at.is_not(None),
                    )
                    .group_by(Charge.case_id)
                )
            ).all()
        )

    items = [
        {
            "case_id": case.id,
            "language": case.language,
            "status": case.status,
            "origin_label": origin_label_short(case),
            "charges_count": charges_count.get(case.id, 0),
            "sustained_count": sustained_count.get(case.id, 0),
            "sentence_progress": {
                "done": sentence_done.get(case.id, 0),
                "total": sentence_total.get(case.id, 0),
            },
            "created_at": case.created_at,
        }
        for case in cases
    ]
    return {"items": items, "page": page, "per_page": per_page, "total": total}


async def rule_frequency(
    session: AsyncSession, catalog: RuleCatalog, user_id: uuid.UUID, limit: int = 5
) -> list[dict]:
    rows = (
        await session.execute(
            select(Charge.rule_id, func.count())
            .select_from(Charge)
            .join(Case, Charge.case_id == Case.id)
            .where(Case.user_id == user_id)
            .group_by(Charge.rule_id)
            .order_by(func.count().desc())
            .limit(limit)
        )
    ).all()
    items = []
    for rule_id, count in rows:
        rule = catalog.get(rule_id)
        items.append({"rule_id": rule_id, "rule_title": rule.title if rule is not None else rule_id, "count": count})
    return items
