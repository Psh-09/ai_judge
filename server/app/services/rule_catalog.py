from pathlib import Path

import yaml
from pydantic import ValidationError

from app.schemas.rule import Rule

REQUIRED_FIELDS = {
    "rule_id",
    "category",
    "title",
    "description",
    "default_severity",
    "typical_effort",
    "languages",
    "active",
}


class RuleCatalogError(Exception):
    """rules.yaml이 스키마를 위반해서 서버를 기동할 수 없을 때 발생한다."""


class RuleCatalog:
    def __init__(self, rules: list[Rule], categories: dict[str, str]):
        self._by_id = {rule.rule_id: rule for rule in rules}
        self._categories = categories

    def get(self, rule_id: str) -> Rule | None:
        """비활성 조항도 포함해 조회한다 (과거 판결의 조항명 표시용)."""
        return self._by_id.get(rule_id)

    def active_rules(self) -> list[Rule]:
        return [rule for rule in self._by_id.values() if rule.active]

    def rules_for_language(self, language: str) -> list[Rule]:
        """활성 조항 중 해당 언어에 적용되는 것만 반환한다. languages가 빈 배열이면 전 언어 공통."""
        return [
            rule
            for rule in self.active_rules()
            if not rule.languages or language in rule.languages
        ]

    @classmethod
    def load(cls, path: Path) -> "RuleCatalog":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        errors: list[str] = []

        categories = raw.get("categories") or {}
        if not categories:
            errors.append("categories 정의가 없습니다.")

        raw_rules = raw.get("rules") or []
        seen_ids: set[str] = set()
        rules: list[Rule] = []

        for idx, item in enumerate(raw_rules):
            if not isinstance(item, dict):
                errors.append(f"[index {idx}] 조항이 객체 형식이 아닙니다.")
                continue

            missing = REQUIRED_FIELDS - item.keys()
            if missing:
                errors.append(f"[index {idx}] 필수 필드 누락: {sorted(missing)}")
                continue

            rule_id = item["rule_id"]
            if rule_id in seen_ids:
                errors.append(f"{rule_id}: rule_id 중복")
                continue

            category = item["category"]
            if category not in categories:
                errors.append(f"{rule_id}: 정의되지 않은 category '{category}'")
                continue

            try:
                rule = Rule(**item)
            except ValidationError as exc:
                errors.append(f"{rule_id}: {exc}")
                continue

            seen_ids.add(rule_id)
            rules.append(rule)

        if errors:
            details = "\n".join(f"- {error}" for error in errors)
            raise RuleCatalogError(f"법전 검증 실패 ({path}):\n{details}")

        return cls(rules, categories)
