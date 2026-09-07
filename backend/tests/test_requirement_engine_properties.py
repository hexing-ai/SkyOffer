from __future__ import annotations

import ast
import json
import socket
import time
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.rules.evaluator import RequirementEngine
from backend.app.rules.registry import RuleVersionConflict, validate_ruleset_registry
from backend.app.schemas.requirement_rules import (
    ApplicantEligibilityInput,
    CourseTag,
    InstitutionTag,
    RequirementRuleSet,
    SubjectTag,
)
from backend.tests.test_requirement_engine import BASE_PROFILE, rule_set


def numeric_rules(minimum: str) -> RequirementRuleSet:
    return rule_set(
        {
            "node_id": "node.academic",
            "operator": "numeric_min",
            "fact_path": "academic_record.value",
            "minimum": minimum,
            "scale": "100",
        }
    )


def test_raising_minimum_cannot_promote_unmet_to_met() -> None:
    profile = ApplicantEligibilityInput.model_validate(
        {**deepcopy(BASE_PROFILE), "academic_record": {"value": "79", "scale": "100"}}
    )
    engine = RequirementEngine()
    assert engine.evaluate(profile, numeric_rules("80")).overall_hard_requirement_status == "unmet"
    assert engine.evaluate(profile, numeric_rules("85")).overall_hard_requirement_status == "unmet"


def test_deleting_fact_cannot_promote_result_to_met() -> None:
    original = ApplicantEligibilityInput.model_validate(
        {**deepcopy(BASE_PROFILE), "academic_record": {"value": "79", "scale": "100"}}
    )
    missing = ApplicantEligibilityInput.model_validate(
        {**deepcopy(BASE_PROFILE), "academic_record": None}
    )
    engine = RequirementEngine()
    assert engine.evaluate(original, numeric_rules("80")).overall_hard_requirement_status == "unmet"
    assert engine.evaluate(missing, numeric_rules("80")).overall_hard_requirement_status == "missing_information"


def test_same_input_is_identical_across_one_hundred_runs() -> None:
    profile = ApplicantEligibilityInput.model_validate(BASE_PROFILE)
    rules = numeric_rules("80")
    engine = RequirementEngine()
    first = engine.evaluate(profile, rules).model_dump_json()
    assert all(engine.evaluate(profile, rules).model_dump_json() == first for _ in range(100))


def test_rule_depth_limit_is_enforced() -> None:
    nested: dict = {"node_id": "node.leaf", "operator": "manual_review"}
    for index in range(21):
        nested = {
            "node_id": f"node.all.{index:02d}",
            "operator": "all",
            "children": [nested],
        }
    with pytest.raises(ValidationError, match="maximum depth"):
        rule_set(nested)


def test_rule_operator_cannot_target_incompatible_fact_path() -> None:
    with pytest.raises(ValidationError):
        rule_set(
            {
                "node_id": "node.invalid",
                "operator": "numeric_min",
                "fact_path": "applicant_region",
                "minimum": 1,
            }
        )


def test_academic_numeric_rule_requires_explicit_scale() -> None:
    with pytest.raises(ValidationError, match="scale is required"):
        rule_set(
            {
                "node_id": "node.invalid",
                "operator": "numeric_min",
                "fact_path": "academic_record.value",
                "minimum": 80,
            }
        )


def test_same_version_different_content_is_rejected_by_registry() -> None:
    with pytest.raises(RuleVersionConflict, match="RULE_VERSION_CONFLICT"):
        validate_ruleset_registry([numeric_rules("80"), numeric_rules("81")])


def test_same_version_same_content_is_registry_idempotent() -> None:
    rules = numeric_rules("80")
    registry = validate_ruleset_registry([rules, rules.model_copy(deep=True)])
    assert len(registry) == 1


def test_evaluator_source_has_no_dynamic_execution_calls() -> None:
    source_path = Path(__file__).parents[1] / "app" / "rules" / "evaluator.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }.intersection({"eval", "exec", "compile", "__import__"})
    assert forbidden == set()


def test_approved_taxonomy_is_versioned_and_enum_complete() -> None:
    path = Path(__file__).parents[1] / "app" / "rules" / "taxonomy_v1.json"
    taxonomy = json.loads(path.read_text(encoding="utf-8"))
    assert taxonomy["taxonomy_version"] == "0.1.0"
    assert taxonomy["review_status"] == "approved"
    assert taxonomy["reviewed_by_role"] == "product_owner_domain_reviewer"
    assert taxonomy["review_date"] == "2026-09-01"
    assert set(taxonomy["subject_tags"]) == {item.value for item in SubjectTag}
    assert set(taxonomy["course_tags"]) == {item.value for item in CourseTag}
    assert set(taxonomy["institution_tags"]) == {item.value for item in InstitutionTag}
    for group in ("subject_tags", "course_tags", "institution_tags"):
        for definition in taxonomy[group].values():
            assert definition["definition"]
            assert definition["examples"]
            assert definition["counterexamples"]


def test_requirement_engine_does_not_need_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args, **kwargs):
        raise AssertionError("network access is forbidden in phase two")

    monkeypatch.setattr(socket, "create_connection", blocked)
    profile = ApplicantEligibilityInput.model_validate(BASE_PROFILE)
    result = RequirementEngine().evaluate(profile, numeric_rules("80"))
    assert result.overall_hard_requirement_status == "met"


def test_core_evaluation_p95_is_below_one_hundred_ms() -> None:
    profile = ApplicantEligibilityInput.model_validate(BASE_PROFILE)
    requirements = []
    for requirement_index in range(100):
        children = [
            {
                "node_id": f"node.r{requirement_index:03d}.n{node_index:02d}",
                "operator": "numeric_min",
                "fact_path": "graduation_year",
                "minimum": 2027,
            }
            for node_index in range(49)
        ]
        requirements.append(
            {
                "requirement_id": f"requirement.perf.{requirement_index:03d}",
                "requirement_type": "degree",
                "is_hard": True,
                "rule": {
                    "node_id": f"node.r{requirement_index:03d}.root",
                    "operator": "all",
                    "children": children,
                },
                "evidence_fixture_ids": [f"evidence.perf.{requirement_index:03d}"],
                "display_text": "合成性能规则",
            }
        )
    rules = RequirementRuleSet.model_validate(
        {
            "schema_version": "requirement_rule_set.v1",
            "ruleset_id": "ruleset.synthetic.performance",
            "ruleset_version": "1.0.0",
            "engine_contract_version": "requirement_engine.v1",
            "synthetic_program_ref": "program.synthetic.performance",
            "requirements": requirements,
        }
    )
    engine = RequirementEngine()
    engine.evaluate(profile, rules)
    samples = []
    for _ in range(20):
        started = time.perf_counter()
        engine.evaluate(profile, rules)
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 <= 100
