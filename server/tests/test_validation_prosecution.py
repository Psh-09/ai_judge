import pytest

from app.services.validation import ProsecutionSchemaError, validate_prosecution
from tests.factories import build_catalog

CATALOG = build_catalog()


def make_charge(**overrides):
    charge = {
        "rule_id": "SEC-HIGH",
        "evidence_lines": [1, 2],
        "charged_severity": "HIGH",
        "severity_adjusted": False,
        "severity_reason": None,
        "description": "설명",
    }
    charge.update(overrides)
    return charge


def test_charge_survives_when_valid():
    result = validate_prosecution(
        [make_charge()], catalog=CATALOG, language="python", total_lines=10
    )
    assert len(result.charges) == 1
    assert result.charges[0].charge_index == 0
    assert result.charges[0].rule_id == "SEC-HIGH"
    assert result.charges_truncated is False


def test_unknown_rule_id_is_discarded():
    result = validate_prosecution(
        [make_charge(rule_id="NO-SUCH-RULE")], catalog=CATALOG, language="python", total_lines=10
    )
    assert result.charges == []


def test_inactive_rule_is_discarded():
    result = validate_prosecution(
        [make_charge(rule_id="OLD-INACTIVE")], catalog=CATALOG, language="python", total_lines=10
    )
    assert result.charges == []


def test_language_mismatch_is_discarded():
    result = validate_prosecution(
        [make_charge(rule_id="PY-ONLY")], catalog=CATALOG, language="javascript", total_lines=10
    )
    assert result.charges == []


def test_language_specific_rule_survives_on_matching_language():
    result = validate_prosecution(
        [make_charge(rule_id="PY-ONLY")], catalog=CATALOG, language="python", total_lines=10
    )
    assert len(result.charges) == 1


def test_common_rule_survives_regardless_of_language():
    result = validate_prosecution(
        [make_charge(rule_id="SEC-HIGH")], catalog=CATALOG, language="cobol", total_lines=10
    )
    assert len(result.charges) == 1


@pytest.mark.parametrize("evidence_lines", [[0, 1], [5, 3], [1, 11]])
def test_evidence_lines_out_of_range_is_discarded(evidence_lines):
    result = validate_prosecution(
        [make_charge(evidence_lines=evidence_lines)],
        catalog=CATALOG,
        language="python",
        total_lines=10,
    )
    assert result.charges == []


def test_evidence_lines_at_exact_boundary_survives():
    result = validate_prosecution(
        [make_charge(evidence_lines=[1, 10])], catalog=CATALOG, language="python", total_lines=10
    )
    assert len(result.charges) == 1


def test_charged_severity_two_steps_from_default_is_discarded():
    # SEC-HIGH의 default_severity는 HIGH, LOW는 2단계 차이
    result = validate_prosecution(
        [make_charge(charged_severity="LOW")], catalog=CATALOG, language="python", total_lines=10
    )
    assert result.charges == []


def test_charged_severity_one_step_from_default_survives():
    result = validate_prosecution(
        [make_charge(rule_id="STRUCT-MED", charged_severity="HIGH")],
        catalog=CATALOG,
        language="python",
        total_lines=10,
    )
    assert len(result.charges) == 1
    assert result.charges[0].charged_severity == "HIGH"


def test_severity_adjusted_with_weak_reason_is_reset_not_discarded():
    result = validate_prosecution(
        [
            make_charge(
                rule_id="STRUCT-MED",
                charged_severity="HIGH",
                severity_adjusted=True,
                severity_reason="짧음",
            )
        ],
        catalog=CATALOG,
        language="python",
        total_lines=10,
    )
    assert len(result.charges) == 1
    charge = result.charges[0]
    assert charge.severity_adjusted is False
    assert charge.charged_severity == "MEDIUM"  # STRUCT-MED의 default
    assert charge.severity_reason is None


def test_severity_adjusted_with_missing_reason_is_reset():
    result = validate_prosecution(
        [
            make_charge(
                rule_id="STRUCT-MED",
                charged_severity="HIGH",
                severity_adjusted=True,
                severity_reason=None,
            )
        ],
        catalog=CATALOG,
        language="python",
        total_lines=10,
    )
    assert result.charges[0].severity_adjusted is False


def test_severity_adjusted_with_valid_reason_is_kept():
    result = validate_prosecution(
        [
            make_charge(
                rule_id="STRUCT-MED",
                charged_severity="HIGH",
                severity_adjusted=True,
                severity_reason="충분히 긴 조정 사유입니다",
            )
        ],
        catalog=CATALOG,
        language="python",
        total_lines=10,
    )
    charge = result.charges[0]
    assert charge.severity_adjusted is True
    assert charge.charged_severity == "HIGH"
    assert charge.severity_reason == "충분히 긴 조정 사유입니다"


def test_duplicate_rule_id_and_start_line_keeps_only_first():
    charges = [
        make_charge(evidence_lines=[1, 2], description="first"),
        make_charge(evidence_lines=[1, 5], description="duplicate start line"),
    ]
    result = validate_prosecution(charges, catalog=CATALOG, language="python", total_lines=10)
    assert len(result.charges) == 1
    assert result.charges[0].description == "first"


def test_same_rule_different_start_line_is_not_a_duplicate():
    charges = [make_charge(evidence_lines=[1, 2]), make_charge(evidence_lines=[3, 4])]
    result = validate_prosecution(charges, catalog=CATALOG, language="python", total_lines=10)
    assert len(result.charges) == 2


def test_charges_over_cap_are_truncated_by_severity_desc():
    charges = [
        make_charge(rule_id="NAMING-LOW", evidence_lines=[i, i], charged_severity="LOW")
        for i in range(1, 11)
    ] + [
        make_charge(rule_id="SEC-HIGH", evidence_lines=[i, i], charged_severity="HIGH")
        for i in range(11, 14)
    ]
    result = validate_prosecution(
        charges, catalog=CATALOG, language="python", total_lines=20, max_charges=12
    )
    assert result.charges_truncated is True
    assert len(result.charges) == 12
    assert all(c.charged_severity == "HIGH" for c in result.charges[:3])
    severities = [c.charged_severity for c in result.charges]
    assert severities == sorted(severities, key=lambda s: {"HIGH": 3, "MEDIUM": 2, "LOW": 1}[s], reverse=True)


def test_charges_at_exactly_cap_are_not_truncated():
    charges = [make_charge(evidence_lines=[i, i]) for i in range(1, 13)]
    result = validate_prosecution(
        charges, catalog=CATALOG, language="python", total_lines=20, max_charges=12
    )
    assert result.charges_truncated is False
    assert len(result.charges) == 12


def test_charge_index_reassigned_from_zero_and_raw_index_preserved():
    charges = [
        make_charge(rule_id="NO-SUCH-RULE"),  # discarded, raw_index 0
        make_charge(evidence_lines=[1, 1]),  # survives, raw_index 1
        make_charge(evidence_lines=[2, 2]),  # survives, raw_index 2
    ]
    result = validate_prosecution(charges, catalog=CATALOG, language="python", total_lines=10)
    assert [c.charge_index for c in result.charges] == [0, 1]
    assert [c.raw_index for c in result.charges] == [1, 2]


def test_zero_surviving_charges_is_a_normal_empty_result():
    result = validate_prosecution(
        [make_charge(rule_id="NO-SUCH-RULE")], catalog=CATALOG, language="python", total_lines=10
    )
    assert result.charges == []
    assert result.charges_truncated is False


def test_malformed_charges_payload_raises_schema_error():
    with pytest.raises(ProsecutionSchemaError):
        validate_prosecution({"not": "a list"}, catalog=CATALOG, language="python", total_lines=10)


def test_charge_missing_required_field_raises_schema_error():
    bad = make_charge()
    del bad["description"]
    with pytest.raises(ProsecutionSchemaError):
        validate_prosecution([bad], catalog=CATALOG, language="python", total_lines=10)


def test_charge_with_invalid_severity_enum_raises_schema_error():
    with pytest.raises(ProsecutionSchemaError):
        validate_prosecution(
            [make_charge(charged_severity="CRITICAL")],
            catalog=CATALOG,
            language="python",
            total_lines=10,
        )
