from __future__ import annotations

from dataclasses import dataclass

from backend.app.rules.canonical import content_hash
from backend.app.schemas.requirement_rules import RequirementRuleSet


@dataclass(slots=True)
class RuleVersionConflict(ValueError):
    ruleset_id: str
    ruleset_version: str
    first_hash: str
    conflicting_hash: str

    def __str__(self) -> str:
        return (
            f"RULE_VERSION_CONFLICT: {self.ruleset_id}@{self.ruleset_version} "
            f"has both {self.first_hash} and {self.conflicting_hash}"
        )


def validate_ruleset_registry(rule_sets: list[RequirementRuleSet]) -> dict[tuple[str, str], str]:
    registry: dict[tuple[str, str], str] = {}
    for rule_set in rule_sets:
        key = (rule_set.ruleset_id, rule_set.ruleset_version)
        digest = content_hash(rule_set)
        previous = registry.get(key)
        if previous is not None and previous != digest:
            raise RuleVersionConflict(
                ruleset_id=rule_set.ruleset_id,
                ruleset_version=rule_set.ruleset_version,
                first_hash=previous,
                conflicting_hash=digest,
            )
        registry[key] = digest
    return registry
