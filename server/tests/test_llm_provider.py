import pytest

from app.fixtures.data import SAMPLE_CODE, SAMPLE_CODE_HASH, SAMPLE_LANGUAGE
from app.services.llm_provider import (
    FixtureLLMProvider,
    FixtureNotFoundError,
    RealLLMProvider,
    Role,
    get_llm_provider,
)
from app.services.rule_catalog import RuleCatalog
from app.services.validation import validate_defense, validate_judgment, validate_prosecution


@pytest.fixture
def catalog():
    return RuleCatalog.load(
        __import__("pathlib").Path(__file__).resolve().parents[2] / "rules.yaml"
    )


async def test_fixture_provider_returns_registered_response():
    provider = FixtureLLMProvider()
    response = await provider.generate(Role.PROSECUTION, {"code_hash": SAMPLE_CODE_HASH})
    assert "charges" in response


async def test_fixture_provider_raises_for_unknown_code_hash():
    provider = FixtureLLMProvider()
    with pytest.raises(FixtureNotFoundError):
        await provider.generate(Role.PROSECUTION, {"code_hash": "unregistered"})


async def test_real_provider_raises_not_implemented():
    provider = RealLLMProvider()
    with pytest.raises(NotImplementedError):
        await provider.generate(Role.PROSECUTION, {"code_hash": SAMPLE_CODE_HASH})


def test_get_llm_provider_selects_by_name():
    assert isinstance(get_llm_provider("fixture"), FixtureLLMProvider)
    assert isinstance(get_llm_provider("real"), RealLLMProvider)
    with pytest.raises(ValueError):
        get_llm_provider("bogus")


async def test_fixture_prosecution_response_survives_validation_with_exactly_5_charges(catalog):
    provider = FixtureLLMProvider()
    raw = await provider.generate(Role.PROSECUTION, {"code_hash": SAMPLE_CODE_HASH})
    total_lines = len(SAMPLE_CODE.split("\n"))

    result = validate_prosecution(
        raw["charges"], catalog=catalog, language=SAMPLE_LANGUAGE, total_lines=total_lines
    )

    assert result.charges_truncated is False
    assert [c.rule_id for c in result.charges] == [
        "SEC-003",
        "STRUCT-001",
        "ERR-002",
        "NAMING-002",
        "STYLE-001",
    ]
    assert [c.charge_index for c in result.charges] == [0, 1, 2, 3, 4]


async def test_fixture_prosecution_response_discards_unknown_rule_and_bad_line_range(catalog):
    provider = FixtureLLMProvider()
    raw = await provider.generate(Role.PROSECUTION, {"code_hash": SAMPLE_CODE_HASH})
    rule_ids = {c["rule_id"] for c in raw["charges"]}
    assert "FAKE-999" in rule_ids
    assert "PERF-001" in rule_ids

    total_lines = len(SAMPLE_CODE.split("\n"))
    result = validate_prosecution(
        raw["charges"], catalog=catalog, language=SAMPLE_LANGUAGE, total_lines=total_lines
    )
    surviving_rule_ids = {c.rule_id for c in result.charges}
    assert "FAKE-999" not in surviving_rule_ids
    assert "PERF-001" not in surviving_rule_ids


async def test_fixture_defense_and_judgment_responses_survive_validation(catalog):
    provider = FixtureLLMProvider()
    total_lines = len(SAMPLE_CODE.split("\n"))

    raw_prosecution = await provider.generate(Role.PROSECUTION, {"code_hash": SAMPLE_CODE_HASH})
    prosecution = validate_prosecution(
        raw_prosecution["charges"],
        catalog=catalog,
        language=SAMPLE_LANGUAGE,
        total_lines=total_lines,
    )

    raw_defense = await provider.generate(Role.DEFENSE, {"code_hash": SAMPLE_CODE_HASH})
    defense = validate_defense(raw_defense["pleas"], charge_count=len(prosecution.charges))
    assert defense.needs_retry is False

    raw_judgment = await provider.generate(Role.JUDGMENT, {"code_hash": SAMPLE_CODE_HASH})
    judgment = validate_judgment(
        raw_judgment,
        charges=prosecution.charges,
        catalog=catalog,
        total_lines=total_lines,
        is_rejudgment=False,
    )
    assert judgment.needs_retry is False
    assert len(judgment.verdicts) == 5
    assert len(judgment.sentences) == 3
