import pytest

from app.schemas.rule import Severity
from app.services.validation import (
    JudgmentSchemaError,
    ValidatedCharge,
    validate_judgment,
)
from tests.factories import build_catalog

CATALOG = build_catalog()


def make_charge(charge_index=0, rule_id="SEC-HIGH", charged_severity=Severity.HIGH):
    return ValidatedCharge(
        charge_index=charge_index,
        raw_index=charge_index,
        rule_id=rule_id,
        evidence_start=1,
        evidence_end=2,
        charged_severity=charged_severity,
        severity_adjusted=False,
        severity_reason=None,
        description="d",
    )


def make_verdict(**overrides):
    verdict = {
        "charge_index": 0,
        "verdict": "SUSTAINED",
        "final_severity": "HIGH",
        "reasoning": "이유",
    }
    verdict.update(overrides)
    return verdict


def make_sentence(**overrides):
    sentence = {
        "charge_index": 0,
        "task": "task",
        "target_lines": [1, 2],
        "effort": "SMALL",
        "effort_adjusted": False,
        "effort_reason": None,
        "rationale": "이유",
    }
    sentence.update(overrides)
    return sentence


def make_judgment(verdicts, sentences, **overrides):
    judgment = {"opinion": "총평", "verdicts": verdicts, "sentences": sentences}
    judgment.update(overrides)
    return judgment


def run(judgment, charges, is_rejudgment=False):
    return validate_judgment(
        judgment, charges=charges, catalog=CATALOG, total_lines=10, is_rejudgment=is_rejudgment
    )


# ── verdict validity ─────────────────────────────────────────────


def test_valid_sustained_verdict_survives():
    result = run(make_judgment([make_verdict()], []), [make_charge()])
    assert result.needs_retry is False
    assert result.verdicts[0].verdict == "SUSTAINED"


def test_sustained_with_mismatched_final_severity_is_treated_as_missing():
    result = run(
        make_judgment([make_verdict(verdict="SUSTAINED", final_severity="MEDIUM")], []),
        [make_charge()],
    )
    assert result.needs_retry is True
    assert result.missing_charge_indices == [0]


def test_reduced_from_high_must_drop_exactly_one_step_to_medium():
    result = run(
        make_judgment([make_verdict(verdict="REDUCED", final_severity="MEDIUM")], []),
        [make_charge(charged_severity=Severity.HIGH)],
    )
    assert result.needs_retry is False
    assert result.verdicts[0].final_severity == "MEDIUM"


def test_reduced_from_high_skipping_to_low_is_treated_as_missing():
    result = run(
        make_judgment([make_verdict(verdict="REDUCED", final_severity="LOW")], []),
        [make_charge(charged_severity=Severity.HIGH)],
    )
    assert result.needs_retry is True
    assert result.missing_charge_indices == [0]


def test_reduced_from_medium_drops_to_low():
    result = run(
        make_judgment([make_verdict(verdict="REDUCED", final_severity="LOW")], []),
        [make_charge(rule_id="STRUCT-MED", charged_severity=Severity.MEDIUM)],
    )
    assert result.needs_retry is False
    assert result.verdicts[0].final_severity == "LOW"


def test_reduced_from_low_stays_low():
    result = run(
        make_judgment([make_verdict(verdict="REDUCED", final_severity="LOW")], []),
        [make_charge(rule_id="NAMING-LOW", charged_severity=Severity.LOW)],
    )
    assert result.needs_retry is False
    assert result.verdicts[0].final_severity == "LOW"


def test_dismissed_must_have_null_final_severity():
    result = run(
        make_judgment([make_verdict(verdict="DISMISSED", final_severity="HIGH")], []),
        [make_charge()],
    )
    assert result.needs_retry is True


def test_dismissed_with_null_final_severity_survives():
    result = run(
        make_judgment([make_verdict(verdict="DISMISSED", final_severity=None)], []),
        [make_charge()],
    )
    assert result.needs_retry is False
    assert result.verdicts[0].final_severity is None


def test_verdict_referencing_nonexistent_charge_index_is_discarded_and_missing():
    result = run(make_judgment([make_verdict(charge_index=5)], []), [make_charge()])
    assert result.needs_retry is True
    assert result.missing_charge_indices == [0]


def test_duplicate_verdict_keeps_first_even_if_first_is_invalid():
    verdicts = [
        make_verdict(verdict="SUSTAINED", final_severity="LOW"),  # invalid, first occurrence
        make_verdict(verdict="SUSTAINED", final_severity="HIGH"),  # would be valid, but ignored
    ]
    result = run(make_judgment(verdicts, []), [make_charge()])
    assert result.needs_retry is True
    assert result.missing_charge_indices == [0]


def test_missing_verdict_for_one_of_several_charges_reports_that_index():
    result = run(
        make_judgment([make_verdict(charge_index=0)], []),
        [make_charge(charge_index=0), make_charge(charge_index=1)],
    )
    assert result.needs_retry is True
    assert result.missing_charge_indices == [1]


# ── sentences ────────────────────────────────────────────────────


def test_sentence_survives_for_sustained_charge():
    result = run(
        make_judgment([make_verdict()], [make_sentence()]),
        [make_charge()],
    )
    assert len(result.sentences) == 1
    assert result.sentences[0].advisory is False


def test_sentence_discarded_for_dismissed_charge():
    result = run(
        make_judgment(
            [make_verdict(verdict="DISMISSED", final_severity=None)],
            [make_sentence()],
        ),
        [make_charge()],
    )
    assert result.sentences == []


def test_sentence_discarded_when_target_lines_out_of_range():
    result = run(
        make_judgment([make_verdict()], [make_sentence(target_lines=[5, 20])]),
        [make_charge()],
    )
    assert result.sentences == []


def test_sentence_discarded_when_target_lines_reversed():
    result = run(
        make_judgment([make_verdict()], [make_sentence(target_lines=[5, 2])]),
        [make_charge()],
    )
    assert result.sentences == []


def test_sentence_effort_adjusted_with_weak_reason_is_reset():
    result = run(
        make_judgment(
            [make_verdict()],
            [make_sentence(effort="LARGE", effort_adjusted=True, effort_reason="짧음")],
        ),
        [make_charge(rule_id="SEC-HIGH")],  # typical_effort = SMALL
    )
    sentence = result.sentences[0]
    assert sentence.effort_adjusted is False
    assert sentence.effort == "SMALL"
    assert sentence.effort_reason is None
    assert sentence.effort_clamped is False


def test_sentence_effort_out_of_range_is_clamped_not_discarded():
    result = run(
        make_judgment([make_verdict()], [make_sentence(effort="SMALL")]),
        [make_charge(rule_id="STRUCT-MED")],  # typical_effort = LARGE, allowed range MEDIUM..LARGE
    )
    sentence = result.sentences[0]
    assert sentence.effort == "MEDIUM"
    assert sentence.effort_clamped is True


def test_sentence_effort_within_range_is_not_clamped():
    result = run(
        make_judgment([make_verdict()], [make_sentence(effort="MEDIUM")]),
        [make_charge(rule_id="STRUCT-MED")],
    )
    sentence = result.sentences[0]
    assert sentence.effort == "MEDIUM"
    assert sentence.effort_clamped is False


def test_reduced_low_severity_sentence_is_advisory():
    result = run(
        make_judgment(
            [make_verdict(verdict="REDUCED", final_severity="LOW")],
            [make_sentence()],
        ),
        [make_charge(rule_id="NAMING-LOW", charged_severity=Severity.LOW)],
    )
    assert result.sentences[0].advisory is True


# ── rebuttal_accepted (재심) ──────────────────────────────────────


def test_rejudgment_missing_rebuttal_accepted_triggers_retry():
    result = run(make_judgment([make_verdict()], []), [make_charge()], is_rejudgment=True)
    assert result.needs_retry is True


def test_rejudgment_with_rebuttal_accepted_present_is_processed():
    result = run(
        make_judgment([make_verdict()], [], rebuttal_accepted=True),
        [make_charge()],
        is_rejudgment=True,
    )
    assert result.needs_retry is False
    assert result.rebuttal_accepted is True


def test_initial_judgment_forces_rebuttal_accepted_to_none():
    result = run(
        make_judgment([make_verdict()], [], rebuttal_accepted=True),
        [make_charge()],
        is_rejudgment=False,
    )
    assert result.rebuttal_accepted is None


# ── schema errors ────────────────────────────────────────────────


def test_malformed_judgment_payload_raises_schema_error():
    with pytest.raises(JudgmentSchemaError):
        run("not a dict", [make_charge()])


def test_verdict_missing_required_field_raises_schema_error():
    bad = make_verdict()
    del bad["reasoning"]
    with pytest.raises(JudgmentSchemaError):
        run(make_judgment([bad], []), [make_charge()])


def test_sentence_missing_required_field_raises_schema_error():
    bad = make_sentence()
    del bad["rationale"]
    with pytest.raises(JudgmentSchemaError):
        run(make_judgment([make_verdict()], [bad]), [make_charge()])
