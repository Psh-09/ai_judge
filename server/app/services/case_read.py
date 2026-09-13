from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, CaseStatus, Charge, Judgment, Plea, Sentence, Verdict
from app.services.case_origin import origin_dict
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

    return {
        "case_id": case.id,
        "language": case.language,
        "status": case.status,
        "revision": case.revision,
        "appeal_used": case.appeal_used,
        "charges_truncated": case.charges_truncated,
        "total_lines": case.total_lines,
        "failed_stage": case.failed_stage,
        "failure_reason": case.failure_reason,
        "origin": origin_dict(case),
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "charges": charge_dicts,
        "pleas": plea_dicts,
        "judgment": judgment_dict,
        "appeal": None,  # 항소 기능은 다음 단계
    }
