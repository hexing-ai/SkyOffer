from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.app.rules.canonical import canonical_json, content_hash
from backend.app.rules.evaluator import RequirementEngine, evaluate_node
from backend.app.schemas.requirement_evaluation import RequirementStatus
from backend.app.schemas.requirement_rules import (
    ApplicantEligibilityInput,
    RequirementRuleSet,
)


BASE_PROFILE = {
    "schema_version": "applicant_eligibility_input.v1",
    "profile_ref": "profile.synthetic.base",
    "applicant_region": "china_mainland",
    "degree_level": "bachelor",
    "degree_status": "in_progress",
    "graduation_year": 2027,
    "degree_subject_tags": ["automation"],
    "institution_tags": ["china_mainland_recognized"],
    "academic_record": {"value": "82.4", "scale": "100"},
    "course_tags": [
        {"course_ref": "course.math", "tags": ["mathematics"]},
        {"course_ref": "course.python", "tags": ["programming"]},
        {"course_ref": "course.ml", "tags": ["machine_learning", "statistics"]},
        {"course_ref": "course.control", "tags": ["control"]},
    ],
    "language_results": [
        {
            "test_type": "ielts",
            "total": "7.0",
            "components": {
                "listening": "7.0",
                "reading": "7.0",
                "writing": "6.0",
                "speaking": "6.5",
            },
        }
    ],
    "work_experience_months": 12,
    "materials": {
        "portfolio": True,
        "interview": None,
        "recommendation_letters": True,
    },
}


def profile(**changes) -> ApplicantEligibilityInput:
    data = deepcopy(BASE_PROFILE)
    data.update(changes)
    return ApplicantEligibilityInput.model_validate(data)


def node(data: dict):
    from backend.app.schemas.requirement_rules import RuleNode

    return TypeAdapter(RuleNode).validate_python(data)


def rule_set(rule: dict, *, applicability: dict | None = None, hard: bool = True):
    return RequirementRuleSet.model_validate(
        {
            "schema_version": "requirement_rule_set.v1",
            "ruleset_id": "ruleset.synthetic.test",
            "ruleset_version": "1.0.0",
            "engine_contract_version": "requirement_engine.v1",
            "synthetic_program_ref": "program.synthetic.test",
            "requirements": [
                {
                    "requirement_id": "requirement.test",
                    "requirement_type": "academic",
                    "is_hard": hard,
                    "applicability": applicability,
                    "rule": rule,
                    "evidence_fixture_ids": ["evidence.synthetic.test"],
                    "display_text": "合成测试要求",
                }
            ],
        }
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("79.999", "unmet"), ("80", "met"), ("80.001", "met")],
)
def test_numeric_minimum_boundaries(value: str, expected: str) -> None:
    candidate = profile(academic_record={"value": value, "scale": "100"})
    rules = rule_set(
        {
            "node_id": "node.academic.min",
            "operator": "numeric_min",
            "fact_path": "academic_record.value",
            "minimum": "80",
            "scale": "100",
        }
    )
    result = RequirementEngine().evaluate(candidate, rules)
    assert result.overall_hard_requirement_status == expected


def test_scale_mismatch_is_manual_review_without_conversion() -> None:
    candidate = profile(academic_record={"value": "3.4", "scale": "4"})
    rules = rule_set(
        {
            "node_id": "node.academic.min",
            "operator": "numeric_min",
            "fact_path": "academic_record.value",
            "minimum": "80",
            "scale": "100",
        }
    )
    result = RequirementEngine().evaluate(candidate, rules)
    check = result.requirement_results[0]
    assert check.status == RequirementStatus.MANUAL_REVIEW
    assert check.reason_code == "SCALE_MISMATCH"


@pytest.mark.parametrize(
    ("operator", "children", "expected"),
    [
        (
            "all",
            [
                {
                    "node_id": "node.fail",
                    "operator": "numeric_min",
                    "fact_path": "graduation_year",
                    "minimum": 2030,
                },
                {
                    "node_id": "node.missing",
                    "operator": "boolean_is",
                    "fact_path": "materials.interview",
                    "expected": True,
                },
            ],
            "unmet",
        ),
        (
            "any",
            [
                {
                    "node_id": "node.pass",
                    "operator": "numeric_min",
                    "fact_path": "graduation_year",
                    "minimum": 2027,
                },
                {
                    "node_id": "node.missing",
                    "operator": "boolean_is",
                    "fact_path": "materials.interview",
                    "expected": True,
                },
            ],
            "met",
        ),
    ],
)
def test_frozen_and_or_precedence(operator: str, children: list[dict], expected: str) -> None:
    trace = evaluate_node(
        profile(),
        node({"node_id": f"node.{operator}", "operator": operator, "children": children}),
    )
    assert trace.status == expected


def test_manual_review_precedes_missing_when_no_conclusive_result() -> None:
    trace = evaluate_node(
        profile(),
        node(
            {
                "node_id": "node.all",
                "operator": "all",
                "children": [
                    {
                        "node_id": "node.manual",
                        "operator": "manual_review",
                    },
                    {
                        "node_id": "node.missing",
                        "operator": "boolean_is",
                        "fact_path": "materials.interview",
                        "expected": True,
                    },
                ],
            }
        ),
    )
    assert trace.status == RequirementStatus.MANUAL_REVIEW


def test_inapplicable_requirement_is_ignored_by_hard_aggregate() -> None:
    rules = rule_set(
        {
            "node_id": "node.rule",
            "operator": "manual_review",
        },
        applicability={
            "node_id": "node.applicability",
            "operator": "enum_in",
            "fact_path": "applicant_region",
            "allowed_values": ["hong_kong"],
        },
    )
    result = RequirementEngine().evaluate(profile(), rules)
    assert result.requirement_results[0].status == RequirementStatus.NOT_APPLICABLE
    assert result.overall_hard_requirement_status == RequirementStatus.NOT_APPLICABLE


def test_case_selects_only_matching_region_branch() -> None:
    rules = rule_set(
        {
            "node_id": "node.case",
            "operator": "case",
            "selector_path": "applicant_region",
            "cases": {
                "china_mainland": {
                    "node_id": "node.china",
                    "operator": "numeric_min",
                    "fact_path": "academic_record.value",
                    "minimum": "80",
                    "scale": "100",
                }
            },
            "default": {
                "node_id": "node.default",
                "operator": "manual_review",
            },
        }
    )
    result = RequirementEngine().evaluate(profile(), rules)
    trace = result.requirement_results[0].trace
    assert trace.status == RequirementStatus.MET
    assert [child.node_id for child in trace.children] == ["node.china"]


def test_missing_case_selector_is_missing_information() -> None:
    rules = rule_set(
        {
            "node_id": "node.case",
            "operator": "case",
            "selector_path": "applicant_region",
            "cases": {
                "china_mainland": {
                    "node_id": "node.china",
                    "operator": "manual_review",
                }
            },
        }
    )
    result = RequirementEngine().evaluate(profile(applicant_region=None), rules)
    assert result.overall_hard_requirement_status == RequirementStatus.MISSING_INFORMATION


def test_language_total_met_but_component_unmet() -> None:
    rules = rule_set(
        {
            "node_id": "node.language",
            "operator": "language_minimum",
            "test_type": "ielts",
            "total_min": "6.5",
            "component_mins": {
                "listening": "6.0",
                "reading": "6.0",
                "writing": "6.5",
                "speaking": "6.0",
            },
        }
    )
    result = RequirementEngine().evaluate(profile(), rules)
    check = result.requirement_results[0]
    assert check.status == RequirementStatus.UNMET
    assert check.reason_code == "LANGUAGE_COMPONENT_UNMET"


def test_language_missing_component_is_missing_information() -> None:
    candidate = profile(
        language_results=[
            {
                "test_type": "ielts",
                "total": "7.0",
                "components": {"listening": "7.0"},
            }
        ]
    )
    rules = rule_set(
        {
            "node_id": "node.language",
            "operator": "language_minimum",
            "test_type": "ielts",
            "total_min": "6.5",
            "component_mins": {"writing": "6.0"},
        }
    )
    result = RequirementEngine().evaluate(candidate, rules)
    assert result.overall_hard_requirement_status == RequirementStatus.MISSING_INFORMATION


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (
            {
                "node_id": "node.subject",
                "operator": "set_intersects",
                "fact_path": "degree_subject_tags",
                "accepted_values": ["automation", "computer_science"],
                "minimum_matches": 1,
            },
            "met",
        ),
        (
            {
                "node_id": "node.courses",
                "operator": "course_group",
                "accepted_tags": ["programming", "machine_learning"],
                "minimum_courses": 2,
            },
            "met",
        ),
        (
            {
                "node_id": "node.work",
                "operator": "duration_min_months",
                "fact_path": "work_experience_months",
                "minimum_months": 24,
            },
            "unmet",
        ),
        (
            {
                "node_id": "node.material",
                "operator": "boolean_is",
                "fact_path": "materials.portfolio",
                "expected": True,
            },
            "met",
        ),
    ],
)
def test_domain_operators(rule: dict, expected: str) -> None:
    result = RequirementEngine().evaluate(profile(), rule_set(rule))
    assert result.overall_hard_requirement_status == expected


def test_same_semantic_input_has_stable_hash_and_output() -> None:
    first = profile(
        degree_subject_tags=["automation", "computer_science"],
        institution_tags=["china_mainland_priority", "china_mainland_recognized"],
    )
    second = profile(
        degree_subject_tags=["computer_science", "automation"],
        institution_tags=["china_mainland_recognized", "china_mainland_priority"],
    )
    rules = rule_set(
        {
            "node_id": "node.degree",
            "operator": "enum_in",
            "fact_path": "degree_level",
            "allowed_values": ["bachelor"],
        }
    )
    engine = RequirementEngine()
    one = engine.evaluate(first, rules)
    two = engine.evaluate(second, rules)
    assert content_hash(first) == content_hash(second)
    assert one == two.model_copy(update={"profile_ref": one.profile_ref})
    assert canonical_json(one) == canonical_json(two)


def test_rule_hash_changes_when_threshold_changes() -> None:
    first = rule_set(
        {
            "node_id": "node.academic",
            "operator": "numeric_min",
            "fact_path": "academic_record.value",
            "minimum": "80",
            "scale": "100",
        }
    )
    second = rule_set(
        {
            "node_id": "node.academic",
            "operator": "numeric_min",
            "fact_path": "academic_record.value",
            "minimum": "81",
            "scale": "100",
        }
    )
    assert content_hash(first) != content_hash(second)


def test_duplicate_node_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate node_id"):
        rule_set(
            {
                "node_id": "node.all",
                "operator": "all",
                "children": [
                    {
                        "node_id": "node.same",
                        "operator": "manual_review",
                    },
                    {
                        "node_id": "node.same",
                        "operator": "manual_review",
                    },
                ],
            }
        )


def test_extra_personal_profile_field_is_rejected() -> None:
    data = deepcopy(BASE_PROFILE)
    data["email"] = "synthetic@example.com"
    with pytest.raises(ValidationError):
        ApplicantEligibilityInput.model_validate(data)
