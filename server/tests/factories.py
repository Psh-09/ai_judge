from app.schemas.rule import Effort, Rule, Severity
from app.services.rule_catalog import RuleCatalog

CATEGORIES = {"SECURITY": "x", "STRUCTURE": "x", "NAMING": "x"}


def build_catalog() -> RuleCatalog:
    rules = [
        Rule(
            rule_id="SEC-HIGH",
            category="SECURITY",
            title="High severity common rule",
            description="d",
            default_severity=Severity.HIGH,
            typical_effort=Effort.SMALL,
            languages=[],
            active=True,
        ),
        Rule(
            rule_id="STRUCT-MED",
            category="STRUCTURE",
            title="Medium severity common rule",
            description="d",
            default_severity=Severity.MEDIUM,
            typical_effort=Effort.LARGE,
            languages=[],
            active=True,
        ),
        Rule(
            rule_id="NAMING-LOW",
            category="NAMING",
            title="Low severity common rule",
            description="d",
            default_severity=Severity.LOW,
            typical_effort=Effort.SMALL,
            languages=[],
            active=True,
        ),
        Rule(
            rule_id="PY-ONLY",
            category="SECURITY",
            title="Python-only rule",
            description="d",
            default_severity=Severity.HIGH,
            typical_effort=Effort.MEDIUM,
            languages=["python"],
            active=True,
        ),
        Rule(
            rule_id="OLD-INACTIVE",
            category="SECURITY",
            title="Deactivated rule",
            description="d",
            default_severity=Severity.LOW,
            typical_effort=Effort.SMALL,
            languages=[],
            active=False,
        ),
    ]
    return RuleCatalog(rules, CATEGORIES)
