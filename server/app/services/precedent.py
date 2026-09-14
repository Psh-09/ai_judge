import uuid
from dataclasses import dataclass

from sqlalchemy import case as sql_case
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Case, CaseStatus, Charge, Judgment, Verdict
from app.services.code import split_lines
from app.services.validation import ValidatedCharge

MAX_PRECEDENTS_PER_CHARGE = 3
MAX_PRECEDENTS_PER_CASE = 10

# plan.md §7 조회는 charged_severity 기준으로 우선순위를 매긴다 (검사 기소 상한과 동일한 랭크).
_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass(frozen=True)
class PrecedentEntry:
    verdict_id: int
    rule_id: str
    charge_index: int  # 현재 사건의 어느 charge를 위해 조회됐는지 (내부 보관용)
    code_snippet: str
    verdict: str
    reasoning: str


@dataclass(frozen=True)
class PrecedentLookupResult:
    entries: list[PrecedentEntry]
    verdict_ids: list[int]


def _extract_snippet(code: str, start: int, end: int) -> str:
    lines = split_lines(code)
    return "\n".join(lines[start - 1 : end])


async def _query_precedents_for_rule(
    session: AsyncSession, *, rule_id: str, language: str, exclude_case_id: uuid.UUID, limit: int
) -> list[tuple[Verdict, Charge, Case]]:
    language_priority = sql_case((Case.language == language, 1), else_=0)
    stmt = (
        select(Verdict, Charge, Case)
        .select_from(Verdict)
        .join(Charge, Verdict.charge_id == Charge.id)
        .join(Judgment, Verdict.judgment_id == Judgment.id)
        .join(Case, Judgment.case_id == Case.id)
        .where(
            Charge.rule_id == rule_id,
            Judgment.is_overturned.is_(False),
            Case.status == CaseStatus.SENTENCED,
            Case.id != exclude_case_id,
        )
        .order_by(language_priority.desc(), Case.created_at.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).all()


async def fetch_precedents(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    language: str,
    charges: list[ValidatedCharge],
) -> PrecedentLookupResult:
    """plan.md §7 그대로: (rule_id, language) 구조화 조회. severity 높은 기소부터 예산(전체 10건)을 채운다."""
    ordered_charges = sorted(
        charges, key=lambda charge: (-_SEVERITY_RANK[charge.charged_severity], charge.charge_index)
    )

    entries: list[PrecedentEntry] = []
    remaining = MAX_PRECEDENTS_PER_CASE
    for charge in ordered_charges:
        if remaining <= 0:
            break
        take = min(MAX_PRECEDENTS_PER_CHARGE, remaining)
        rows = await _query_precedents_for_rule(
            session, rule_id=charge.rule_id, language=language, exclude_case_id=case_id, limit=take
        )
        for verdict, precedent_charge, precedent_case in rows:
            entries.append(
                PrecedentEntry(
                    verdict_id=verdict.id,
                    rule_id=precedent_charge.rule_id,
                    charge_index=charge.charge_index,
                    code_snippet=_extract_snippet(
                        precedent_case.code, precedent_charge.evidence_start, precedent_charge.evidence_end
                    ),
                    verdict=verdict.verdict,
                    reasoning=verdict.reasoning,
                )
            )
        remaining -= len(rows)

    return PrecedentLookupResult(entries=entries, verdict_ids=[e.verdict_id for e in entries])


def precedent_summaries_for_prompt(result: PrecedentLookupResult) -> list[dict]:
    """판사 프롬프트에 넣을 요약 (rule_id, 코드 스니펫 발췌, verdict, reasoning)."""
    return [
        {
            "rule_id": entry.rule_id,
            "code_snippet": entry.code_snippet,
            "verdict": entry.verdict,
            "reasoning": entry.reasoning,
        }
        for entry in result.entries
    ]
