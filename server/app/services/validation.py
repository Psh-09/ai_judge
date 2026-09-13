from dataclasses import dataclass
from enum import Enum

from app.schemas.rule import Effort, Severity
from app.services.rule_catalog import RuleCatalog

MAX_CHARGES = 12
MIN_REASON_LENGTH = 10

_SEVERITY_RANK = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}
_EFFORT_RANK = {Effort.SMALL: 1, Effort.MEDIUM: 2, Effort.LARGE: 3}
_RANK_TO_EFFORT = {rank: effort for effort, rank in _EFFORT_RANK.items()}


def _is_valid_reason(reason: str | None, min_length: int = MIN_REASON_LENGTH) -> bool:
    return bool(reason) and len(reason.strip()) >= min_length


class PleaValue(str, Enum):
    ADMIT = "ADMIT"
    DENY = "DENY"
    NO_RESPONSE = "NO_RESPONSE"


class VerdictValue(str, Enum):
    SUSTAINED = "SUSTAINED"
    REDUCED = "REDUCED"
    DISMISSED = "DISMISSED"


# ── 검사(Prosecution) ────────────────────────────────────────────


class ProsecutionSchemaError(Exception):
    """검사 출력의 JSON 형태 자체가 스키마를 안 갖췄을 때. 스테이지 재시도 신호다."""


@dataclass(frozen=True)
class ValidatedCharge:
    charge_index: int
    raw_index: int  # 내부 보관용. API/DB에는 노출하지 않는다.
    rule_id: str
    evidence_start: int
    evidence_end: int
    charged_severity: Severity
    severity_adjusted: bool
    severity_reason: str | None
    description: str


@dataclass(frozen=True)
class ProsecutionResult:
    charges: list[ValidatedCharge]
    charges_truncated: bool


@dataclass(frozen=True)
class _RawCharge:
    rule_id: str
    evidence_start: int
    evidence_end: int
    charged_severity: Severity
    severity_adjusted: bool
    severity_reason: str | None
    description: str


def _parse_raw_charge(item: object) -> _RawCharge:
    if not isinstance(item, dict):
        raise ProsecutionSchemaError("charge 항목이 객체가 아닙니다.")
    try:
        rule_id = item["rule_id"]
        evidence_lines = item["evidence_lines"]
        charged_severity_raw = item["charged_severity"]
        severity_adjusted = item["severity_adjusted"]
        description = item["description"]
    except KeyError as exc:
        raise ProsecutionSchemaError(f"필수 필드 누락: {exc}") from exc
    severity_reason = item.get("severity_reason")

    if not isinstance(rule_id, str):
        raise ProsecutionSchemaError("rule_id는 문자열이어야 합니다.")
    if (
        not isinstance(evidence_lines, list)
        or len(evidence_lines) != 2
        or not all(isinstance(n, int) for n in evidence_lines)
    ):
        raise ProsecutionSchemaError("evidence_lines는 [start, end] 정수 쌍이어야 합니다.")
    if not isinstance(severity_adjusted, bool):
        raise ProsecutionSchemaError("severity_adjusted는 boolean이어야 합니다.")
    if not isinstance(description, str):
        raise ProsecutionSchemaError("description은 문자열이어야 합니다.")
    try:
        charged_severity = Severity(charged_severity_raw)
    except ValueError as exc:
        raise ProsecutionSchemaError(f"잘못된 charged_severity 값: {charged_severity_raw}") from exc

    start, end = evidence_lines
    return _RawCharge(
        rule_id=rule_id,
        evidence_start=start,
        evidence_end=end,
        charged_severity=charged_severity,
        severity_adjusted=severity_adjusted,
        severity_reason=severity_reason,
        description=description,
    )


def _within_one_severity_step(charged: Severity, default: Severity) -> bool:
    return abs(_SEVERITY_RANK[charged] - _SEVERITY_RANK[default]) <= 1


def validate_prosecution(
    raw_charges: object,
    *,
    catalog: RuleCatalog,
    language: str,
    total_lines: int,
    max_charges: int = MAX_CHARGES,
) -> ProsecutionResult:
    if not isinstance(raw_charges, list):
        raise ProsecutionSchemaError("charges는 리스트여야 합니다.")

    survivors: list[ValidatedCharge] = []
    seen_keys: set[tuple[str, int]] = set()

    for raw_index, item in enumerate(raw_charges):
        fields = _parse_raw_charge(item)

        rule = catalog.get(fields.rule_id)
        if rule is None or not rule.active:
            continue
        if rule.languages and language not in rule.languages:
            continue

        if not (1 <= fields.evidence_start <= fields.evidence_end <= total_lines):
            continue

        if not _within_one_severity_step(fields.charged_severity, rule.default_severity):
            continue

        charged_severity = fields.charged_severity
        severity_adjusted = fields.severity_adjusted
        severity_reason = fields.severity_reason
        if severity_adjusted and not _is_valid_reason(severity_reason):
            charged_severity = rule.default_severity
            severity_adjusted = False
            severity_reason = None

        dedup_key = (fields.rule_id, fields.evidence_start)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        survivors.append(
            ValidatedCharge(
                charge_index=-1,  # 아래에서 재부여
                raw_index=raw_index,
                rule_id=fields.rule_id,
                evidence_start=fields.evidence_start,
                evidence_end=fields.evidence_end,
                charged_severity=charged_severity,
                severity_adjusted=severity_adjusted,
                severity_reason=severity_reason,
                description=fields.description,
            )
        )

    charges_truncated = False
    if len(survivors) > max_charges:
        survivors = sorted(
            survivors, key=lambda c: _SEVERITY_RANK[c.charged_severity], reverse=True
        )[:max_charges]
        charges_truncated = True

    reindexed = [
        ValidatedCharge(
            charge_index=idx,
            raw_index=charge.raw_index,
            rule_id=charge.rule_id,
            evidence_start=charge.evidence_start,
            evidence_end=charge.evidence_end,
            charged_severity=charge.charged_severity,
            severity_adjusted=charge.severity_adjusted,
            severity_reason=charge.severity_reason,
            description=charge.description,
        )
        for idx, charge in enumerate(survivors)
    ]

    return ProsecutionResult(charges=reindexed, charges_truncated=charges_truncated)


# ── 변호인(Defense) ──────────────────────────────────────────────


class DefenseSchemaError(Exception):
    """변호인 출력의 JSON 형태 자체가 스키마를 안 갖췄을 때. 스테이지 재시도 신호다."""


@dataclass(frozen=True)
class ValidatedPlea:
    charge_index: int
    plea: PleaValue
    argument: str


@dataclass(frozen=True)
class DefenseResult:
    pleas: list[ValidatedPlea]
    needs_retry: bool  # 전부 NO_RESPONSE로 채워졌을 때 (대립 구조 붕괴)


@dataclass(frozen=True)
class _RawPlea:
    charge_index: int
    plea: PleaValue
    argument: str


def _parse_raw_plea(item: object) -> _RawPlea:
    if not isinstance(item, dict):
        raise DefenseSchemaError("plea 항목이 객체가 아닙니다.")
    try:
        charge_index = item["charge_index"]
        plea_raw = item["plea"]
        argument = item["argument"]
    except KeyError as exc:
        raise DefenseSchemaError(f"필수 필드 누락: {exc}") from exc
    if not isinstance(charge_index, int):
        raise DefenseSchemaError("charge_index는 정수여야 합니다.")
    if not isinstance(argument, str):
        raise DefenseSchemaError("argument는 문자열이어야 합니다.")
    try:
        plea = PleaValue(plea_raw)
    except ValueError as exc:
        raise DefenseSchemaError(f"잘못된 plea 값: {plea_raw}") from exc
    return _RawPlea(charge_index=charge_index, plea=plea, argument=argument)


def validate_defense(raw_pleas: object, *, charge_count: int) -> DefenseResult:
    if not isinstance(raw_pleas, list):
        raise DefenseSchemaError("pleas는 리스트여야 합니다.")

    by_index: dict[int, _RawPlea] = {}
    for item in raw_pleas:
        parsed = _parse_raw_plea(item)
        if not (0 <= parsed.charge_index < charge_count):
            continue  # 존재하지 않는 charge_index 참조 → 폐기
        if parsed.charge_index in by_index:
            continue  # 중복 참조 → 첫 항목만 인정
        by_index[parsed.charge_index] = parsed

    pleas = [
        ValidatedPlea(
            charge_index=idx,
            plea=by_index[idx].plea if idx in by_index else PleaValue.NO_RESPONSE,
            argument=by_index[idx].argument if idx in by_index else "",
        )
        for idx in range(charge_count)
    ]

    needs_retry = charge_count > 0 and all(p.plea == PleaValue.NO_RESPONSE for p in pleas)
    return DefenseResult(pleas=pleas, needs_retry=needs_retry)


# ── 판사(Judgment, 재심 공통) ─────────────────────────────────────


class JudgmentSchemaError(Exception):
    """판사 출력의 JSON 형태 자체가 스키마를 안 갖췄을 때. 스테이지 재시도 신호다."""


@dataclass(frozen=True)
class ValidatedVerdict:
    charge_index: int
    verdict: VerdictValue
    final_severity: Severity | None
    reasoning: str


@dataclass(frozen=True)
class ValidatedSentence:
    charge_index: int
    task: str
    target_start: int
    target_end: int
    effort: Effort
    effort_adjusted: bool
    effort_reason: str | None
    effort_clamped: bool
    advisory: bool
    rationale: str


@dataclass(frozen=True)
class JudgmentResult:
    opinion: str
    rebuttal_accepted: bool | None
    verdicts: list[ValidatedVerdict]
    sentences: list[ValidatedSentence]
    needs_retry: bool
    missing_charge_indices: list[int]  # 재시도 프롬프트에 구체적으로 명시할 인덱스


@dataclass(frozen=True)
class _RawVerdict:
    charge_index: int
    verdict: VerdictValue
    final_severity: Severity | None
    reasoning: str


def _parse_raw_verdict(item: object) -> _RawVerdict:
    if not isinstance(item, dict):
        raise JudgmentSchemaError("verdict 항목이 객체가 아닙니다.")
    try:
        charge_index = item["charge_index"]
        verdict_raw = item["verdict"]
        final_severity_raw = item["final_severity"]
        reasoning = item["reasoning"]
    except KeyError as exc:
        raise JudgmentSchemaError(f"필수 필드 누락: {exc}") from exc
    if not isinstance(charge_index, int):
        raise JudgmentSchemaError("charge_index는 정수여야 합니다.")
    if not isinstance(reasoning, str):
        raise JudgmentSchemaError("reasoning은 문자열이어야 합니다.")
    try:
        verdict = VerdictValue(verdict_raw)
    except ValueError as exc:
        raise JudgmentSchemaError(f"잘못된 verdict 값: {verdict_raw}") from exc
    final_severity = None
    if final_severity_raw is not None:
        try:
            final_severity = Severity(final_severity_raw)
        except ValueError as exc:
            raise JudgmentSchemaError(f"잘못된 final_severity 값: {final_severity_raw}") from exc
    return _RawVerdict(
        charge_index=charge_index,
        verdict=verdict,
        final_severity=final_severity,
        reasoning=reasoning,
    )


def _is_valid_verdict(parsed: _RawVerdict, charged_severity: Severity) -> bool:
    """final_severity <= charged_severity(상승 불가), REDUCED/SUSTAINED/DISMISSED별 규칙을 만족하는가."""
    if parsed.verdict == VerdictValue.DISMISSED:
        return parsed.final_severity is None
    if parsed.verdict == VerdictValue.SUSTAINED:
        return parsed.final_severity == charged_severity
    if charged_severity == Severity.HIGH:
        return parsed.final_severity == Severity.MEDIUM
    if charged_severity == Severity.MEDIUM:
        return parsed.final_severity == Severity.LOW
    return parsed.final_severity == Severity.LOW  # charged_severity == LOW


@dataclass(frozen=True)
class _RawSentence:
    charge_index: int
    task: str
    target_start: int
    target_end: int
    effort: Effort
    effort_adjusted: bool
    effort_reason: str | None
    rationale: str


def _parse_raw_sentence(item: object) -> _RawSentence:
    if not isinstance(item, dict):
        raise JudgmentSchemaError("sentence 항목이 객체가 아닙니다.")
    try:
        charge_index = item["charge_index"]
        task = item["task"]
        target_lines = item["target_lines"]
        effort_raw = item["effort"]
        effort_adjusted = item["effort_adjusted"]
        rationale = item["rationale"]
    except KeyError as exc:
        raise JudgmentSchemaError(f"필수 필드 누락: {exc}") from exc
    effort_reason = item.get("effort_reason")

    if not isinstance(charge_index, int):
        raise JudgmentSchemaError("charge_index는 정수여야 합니다.")
    if not isinstance(task, str):
        raise JudgmentSchemaError("task는 문자열이어야 합니다.")
    if (
        not isinstance(target_lines, list)
        or len(target_lines) != 2
        or not all(isinstance(n, int) for n in target_lines)
    ):
        raise JudgmentSchemaError("target_lines는 [start, end] 정수 쌍이어야 합니다.")
    if not isinstance(effort_adjusted, bool):
        raise JudgmentSchemaError("effort_adjusted는 boolean이어야 합니다.")
    if not isinstance(rationale, str):
        raise JudgmentSchemaError("rationale은 문자열이어야 합니다.")
    try:
        effort = Effort(effort_raw)
    except ValueError as exc:
        raise JudgmentSchemaError(f"잘못된 effort 값: {effort_raw}") from exc

    target_start, target_end = target_lines
    return _RawSentence(
        charge_index=charge_index,
        task=task,
        target_start=target_start,
        target_end=target_end,
        effort=effort,
        effort_adjusted=effort_adjusted,
        effort_reason=effort_reason,
        rationale=rationale,
    )


def _clamp_effort(effort: Effort, typical: Effort) -> Effort:
    typical_rank = _EFFORT_RANK[typical]
    low = max(1, typical_rank - 1)
    high = min(3, typical_rank + 1)
    clamped_rank = min(max(_EFFORT_RANK[effort], low), high)
    return _RANK_TO_EFFORT[clamped_rank]


def validate_judgment(
    raw_judgment: object,
    *,
    charges: list[ValidatedCharge],
    catalog: RuleCatalog,
    total_lines: int,
    is_rejudgment: bool = False,
) -> JudgmentResult:
    if not isinstance(raw_judgment, dict):
        raise JudgmentSchemaError("judgment는 객체여야 합니다.")
    try:
        opinion = raw_judgment["opinion"]
        raw_verdicts = raw_judgment["verdicts"]
        raw_sentences = raw_judgment["sentences"]
    except KeyError as exc:
        raise JudgmentSchemaError(f"필수 필드 누락: {exc}") from exc
    if not isinstance(opinion, str):
        raise JudgmentSchemaError("opinion은 문자열이어야 합니다.")
    if not isinstance(raw_verdicts, list) or not isinstance(raw_sentences, list):
        raise JudgmentSchemaError("verdicts/sentences는 리스트여야 합니다.")

    rebuttal_accepted_raw = raw_judgment.get("rebuttal_accepted")
    if is_rejudgment and rebuttal_accepted_raw is None:
        return JudgmentResult(
            opinion=opinion,
            rebuttal_accepted=None,
            verdicts=[],
            sentences=[],
            needs_retry=True,
            missing_charge_indices=[],
        )
    rebuttal_accepted = bool(rebuttal_accepted_raw) if is_rejudgment else None

    charge_by_index = {charge.charge_index: charge for charge in charges}

    candidates: dict[int, _RawVerdict] = {}
    for item in raw_verdicts:
        parsed = _parse_raw_verdict(item)
        if parsed.charge_index not in charge_by_index:
            continue  # 존재하지 않는 charge_index 참조 → 폐기
        if parsed.charge_index in candidates:
            continue  # 중복 참조 → 첫 항목만 인정 (이후 등장은 무효한 첫 항목도 되살리지 않음)
        candidates[parsed.charge_index] = parsed

    accepted_verdicts: dict[int, ValidatedVerdict] = {}
    for idx, parsed in candidates.items():
        charge = charge_by_index[idx]
        if not _is_valid_verdict(parsed, charge.charged_severity):
            continue
        accepted_verdicts[idx] = ValidatedVerdict(
            charge_index=idx,
            verdict=parsed.verdict,
            final_severity=parsed.final_severity,
            reasoning=parsed.reasoning,
        )

    missing = sorted(set(charge_by_index) - set(accepted_verdicts))
    if missing:
        # 서버가 누락분을 대신 채우지 않는다 (부분 판결 금지). 재시도 프롬프트가 missing_charge_indices를 명시한다.
        return JudgmentResult(
            opinion=opinion,
            rebuttal_accepted=rebuttal_accepted,
            verdicts=[accepted_verdicts[idx] for idx in sorted(accepted_verdicts)],
            sentences=[],
            needs_retry=True,
            missing_charge_indices=missing,
        )

    sentenceable = {
        idx
        for idx, verdict in accepted_verdicts.items()
        if verdict.verdict in (VerdictValue.SUSTAINED, VerdictValue.REDUCED)
    }

    sentences: list[ValidatedSentence] = []
    for item in raw_sentences:
        parsed = _parse_raw_sentence(item)
        if parsed.charge_index not in sentenceable:
            continue
        if not (1 <= parsed.target_start <= parsed.target_end <= total_lines):
            continue

        charge = charge_by_index[parsed.charge_index]
        rule = catalog.get(charge.rule_id)
        typical_effort = rule.typical_effort

        effort = parsed.effort
        effort_adjusted = parsed.effort_adjusted
        effort_reason = parsed.effort_reason
        effort_clamped = False
        if effort_adjusted and not _is_valid_reason(effort_reason):
            effort = typical_effort
            effort_adjusted = False
            effort_reason = None
        else:
            clamped = _clamp_effort(effort, typical_effort)
            if clamped != effort:
                effort = clamped
                effort_clamped = True

        advisory = (
            charge.charged_severity == Severity.LOW
            and accepted_verdicts[parsed.charge_index].verdict == VerdictValue.REDUCED
        )

        sentences.append(
            ValidatedSentence(
                charge_index=parsed.charge_index,
                task=parsed.task,
                target_start=parsed.target_start,
                target_end=parsed.target_end,
                effort=effort,
                effort_adjusted=effort_adjusted,
                effort_reason=effort_reason,
                effort_clamped=effort_clamped,
                advisory=advisory,
                rationale=parsed.rationale,
            )
        )

    return JudgmentResult(
        opinion=opinion,
        rebuttal_accepted=rebuttal_accepted,
        verdicts=[accepted_verdicts[idx] for idx in sorted(accepted_verdicts)],
        sentences=sentences,
        needs_retry=False,
        missing_charge_indices=[],
    )
