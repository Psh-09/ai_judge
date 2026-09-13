import pytest

from app.services.validation import DefenseSchemaError, PleaValue, validate_defense


def make_plea(**overrides):
    plea = {"charge_index": 0, "plea": "DENY", "argument": "반박 근거"}
    plea.update(overrides)
    return plea


def test_all_charges_covered_survive_as_is():
    result = validate_defense([make_plea(charge_index=0), make_plea(charge_index=1)], charge_count=2)
    assert [p.plea for p in result.pleas] == [PleaValue.DENY, PleaValue.DENY]
    assert result.needs_retry is False


def test_charge_index_not_referenced_is_autofilled_no_response():
    result = validate_defense([make_plea(charge_index=0)], charge_count=2)
    assert result.pleas[0].plea == PleaValue.DENY
    assert result.pleas[1].plea == PleaValue.NO_RESPONSE
    assert result.pleas[1].argument == ""


def test_nonexistent_charge_index_is_discarded():
    result = validate_defense([make_plea(charge_index=5)], charge_count=2)
    assert all(p.plea == PleaValue.NO_RESPONSE for p in result.pleas)


def test_duplicate_charge_index_keeps_only_first():
    pleas = [
        make_plea(charge_index=0, argument="first"),
        make_plea(charge_index=0, argument="second"),
    ]
    result = validate_defense(pleas, charge_count=1)
    assert result.pleas[0].argument == "first"


def test_all_no_response_triggers_retry():
    result = validate_defense([], charge_count=2)
    assert result.needs_retry is True


def test_partial_no_response_does_not_trigger_retry():
    result = validate_defense([make_plea(charge_index=0)], charge_count=2)
    assert result.needs_retry is False


def test_zero_charges_never_triggers_retry():
    result = validate_defense([], charge_count=0)
    assert result.needs_retry is False
    assert result.pleas == []


def test_malformed_pleas_payload_raises_schema_error():
    with pytest.raises(DefenseSchemaError):
        validate_defense("not a list", charge_count=1)


def test_plea_missing_required_field_raises_schema_error():
    bad = make_plea()
    del bad["argument"]
    with pytest.raises(DefenseSchemaError):
        validate_defense([bad], charge_count=1)


def test_plea_with_invalid_enum_raises_schema_error():
    with pytest.raises(DefenseSchemaError):
        validate_defense([make_plea(plea="MAYBE")], charge_count=1)
