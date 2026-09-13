import pytest

from app.config import BASE_DIR
from app.services.rule_catalog import RuleCatalog, RuleCatalogError

VALID_YAML = """
categories:
  SECURITY: 외부 입력을 신뢰하는 지점
rules:
  - rule_id: SEC-001
    category: SECURITY
    title: 하드코딩된 자격증명
    description: 설명
    default_severity: HIGH
    typical_effort: SMALL
    languages: []
    active: true
  - rule_id: SEC-002
    category: SECURITY
    title: 언어 한정 조항
    description: 설명
    default_severity: LOW
    typical_effort: SMALL
    languages: [python]
    active: false
"""


def write(tmp_path, content):
    path = tmp_path / "rules.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_real_rules_yaml():
    catalog = RuleCatalog.load(BASE_DIR / "rules.yaml")
    active = catalog.active_rules()
    assert len(active) == 20
    assert all(rule.active for rule in active)


def test_get_returns_inactive_rule_too(tmp_path):
    catalog = RuleCatalog.load(write(tmp_path, VALID_YAML))
    assert catalog.get("SEC-002") is not None
    assert catalog.get("SEC-002").active is False
    assert catalog.get("NO-SUCH-ID") is None


def test_active_rules_excludes_inactive(tmp_path):
    catalog = RuleCatalog.load(write(tmp_path, VALID_YAML))
    ids = {rule.rule_id for rule in catalog.active_rules()}
    assert ids == {"SEC-001"}


def test_rules_for_language_includes_common_and_matching(tmp_path):
    catalog = RuleCatalog.load(write(tmp_path, VALID_YAML))
    ids = {rule.rule_id for rule in catalog.rules_for_language("python")}
    assert ids == {"SEC-001"}  # SEC-002는 active=false라 제외됨


def test_duplicate_rule_id_fails(tmp_path):
    content = VALID_YAML + """
  - rule_id: SEC-001
    category: SECURITY
    title: 중복
    description: 설명
    default_severity: LOW
    typical_effort: SMALL
    languages: []
    active: true
"""
    with pytest.raises(RuleCatalogError, match="rule_id 중복"):
        RuleCatalog.load(write(tmp_path, content))


def test_missing_required_field_fails(tmp_path):
    content = """
categories:
  SECURITY: 외부 입력을 신뢰하는 지점
rules:
  - rule_id: SEC-001
    category: SECURITY
    title: 제목
    description: 설명
    default_severity: HIGH
    typical_effort: SMALL
    active: true
"""
    with pytest.raises(RuleCatalogError, match="필수 필드 누락"):
        RuleCatalog.load(write(tmp_path, content))


def test_invalid_severity_enum_fails(tmp_path):
    content = """
categories:
  SECURITY: 외부 입력을 신뢰하는 지점
rules:
  - rule_id: SEC-001
    category: SECURITY
    title: 제목
    description: 설명
    default_severity: CRITICAL
    typical_effort: SMALL
    languages: []
    active: true
"""
    with pytest.raises(RuleCatalogError):
        RuleCatalog.load(write(tmp_path, content))


def test_undefined_category_fails(tmp_path):
    content = """
categories:
  SECURITY: 외부 입력을 신뢰하는 지점
rules:
  - rule_id: SEC-001
    category: NOT_A_CATEGORY
    title: 제목
    description: 설명
    default_severity: HIGH
    typical_effort: SMALL
    languages: []
    active: true
"""
    with pytest.raises(RuleCatalogError, match="정의되지 않은 category"):
        RuleCatalog.load(write(tmp_path, content))
