from __future__ import annotations

import hashlib
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.app.rules.canonical import content_hash
from backend.app.schemas.requirement_evaluation import (
    NodeTrace,
    RequirementEvaluation,
    RequirementResult,
    RequirementStatus,
)
from backend.app.schemas.requirement_rules import (
    AllRule,
    AnyRule,
    ApplicantEligibilityInput,
    BooleanIsRule,
    CaseRule,
    CourseGroupRule,
    DurationMinMonthsRule,
    EnumInRule,
    FactPath,
    LanguageMinimumRule,
    ManualReviewRule,
    NumericMaxRule,
    NumericMinRule,
    RequirementFixture,
    RequirementRuleSet,
    RuleNode,
    SetIntersectsRule,
)


ENGINE_VERSION = "requirement_engine.v1.0.0"


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, (set, frozenset)):
        return sorted(_json_value(item) for item in value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(_json_value(key)): _json_value(item) for key, item in value.items()}
    return value


def _fact(profile: ApplicantEligibilityInput, path: FactPath) -> Any:
    mapping = {
        FactPath.APPLICANT_REGION: profile.applicant_region,
        FactPath.DEGREE_LEVEL: profile.degree_level,
        FactPath.DEGREE_STATUS: profile.degree_status,
        FactPath.GRADUATION_YEAR: profile.graduation_year,
        FactPath.DEGREE_SUBJECT_TAGS: profile.degree_subject_tags,
        FactPath.INSTITUTION_TAGS: profile.institution_tags,
        FactPath.ACADEMIC_VALUE: (
            profile.academic_record.value if profile.academic_record else None
        ),
        FactPath.WORK_EXPERIENCE_MONTHS: profile.work_experience_months,
        FactPath.MATERIAL_PORTFOLIO: profile.materials.portfolio,
        FactPath.MATERIAL_INTERVIEW: profile.materials.interview,
        FactPath.MATERIAL_RECOMMENDATION_LETTERS: (
            profile.materials.recommendation_letters
        ),
    }
    return mapping[path]


def _trace(
    node: RuleNode,
    status: RequirementStatus,
    reason_code: str,
    *,
    facts: dict[str, Any] | None = None,
    expected: dict[str, Any] | None = None,
    children: list[NodeTrace] | None = None,
) -> NodeTrace:
    return NodeTrace(
        node_id=node.node_id,
        operator=node.operator,
        status=status,
        reason_code=reason_code,
        facts_read=_json_value(facts or {}),
        expected=_json_value(expected or {}),
        children=children or [],
    )


def _all_status(children: list[NodeTrace]) -> RequirementStatus:
    statuses = {child.status for child in children}
    if RequirementStatus.UNMET in statuses:
        return RequirementStatus.UNMET
    if RequirementStatus.MANUAL_REVIEW in statuses:
        return RequirementStatus.MANUAL_REVIEW
    if RequirementStatus.MISSING_INFORMATION in statuses:
        return RequirementStatus.MISSING_INFORMATION
    return RequirementStatus.MET


def _any_status(children: list[NodeTrace]) -> RequirementStatus:
    statuses = {child.status for child in children}
    if RequirementStatus.MET in statuses:
        return RequirementStatus.MET
    if RequirementStatus.MANUAL_REVIEW in statuses:
        return RequirementStatus.MANUAL_REVIEW
    if RequirementStatus.MISSING_INFORMATION in statuses:
        return RequirementStatus.MISSING_INFORMATION
    return RequirementStatus.UNMET


def _numeric_scale_status(
    profile: ApplicantEligibilityInput, node: NumericMinRule | NumericMaxRule
) -> NodeTrace | None:
    if node.fact_path != FactPath.ACADEMIC_VALUE or node.scale is None:
        return None
    if profile.academic_record is None:
        return None
    actual_scale = profile.academic_record.scale
    if actual_scale != node.scale:
        return _trace(
            node,
            RequirementStatus.MANUAL_REVIEW,
            "SCALE_MISMATCH",
            facts={"academic_record.scale": actual_scale},
            expected={"scale": node.scale},
        )
    return None


def evaluate_node(profile: ApplicantEligibilityInput, node: RuleNode) -> NodeTrace:
    if isinstance(node, AllRule):
        children = [evaluate_node(profile, child) for child in node.children]
        return _trace(node, _all_status(children), "ALL_AGGREGATED", children=children)

    if isinstance(node, AnyRule):
        children = [evaluate_node(profile, child) for child in node.children]
        return _trace(node, _any_status(children), "ANY_AGGREGATED", children=children)

    if isinstance(node, (NumericMinRule, NumericMaxRule)):
        scale_result = _numeric_scale_status(profile, node)
        if scale_result is not None:
            return scale_result
        value = _fact(profile, node.fact_path)
        if value is None:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={node.fact_path.value: None},
            )
        if isinstance(node, NumericMinRule):
            met = Decimal(value) >= node.minimum
            return _trace(
                node,
                RequirementStatus.MET if met else RequirementStatus.UNMET,
                "VALUE_AT_OR_ABOVE_MIN" if met else "VALUE_BELOW_MIN",
                facts={node.fact_path.value: value},
                expected={"minimum": node.minimum, "scale": node.scale},
            )
        met = Decimal(value) <= node.maximum
        return _trace(
            node,
            RequirementStatus.MET if met else RequirementStatus.UNMET,
            "VALUE_AT_OR_BELOW_MAX" if met else "VALUE_ABOVE_MAX",
            facts={node.fact_path.value: value},
            expected={"maximum": node.maximum, "scale": node.scale},
        )

    if isinstance(node, EnumInRule):
        value = _fact(profile, node.fact_path)
        if value is None:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={node.fact_path.value: None},
            )
        actual = _json_value(value)
        met = str(actual) in node.allowed_values
        return _trace(
            node,
            RequirementStatus.MET if met else RequirementStatus.UNMET,
            "ENUM_ALLOWED" if met else "ENUM_NOT_ALLOWED",
            facts={node.fact_path.value: actual},
            expected={"allowed_values": node.allowed_values},
        )

    if isinstance(node, SetIntersectsRule):
        values = _fact(profile, node.fact_path)
        if not values:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={node.fact_path.value: []},
            )
        actual = {str(_json_value(value)) for value in values}
        matches = actual.intersection(node.accepted_values)
        met = len(matches) >= node.minimum_matches
        return _trace(
            node,
            RequirementStatus.MET if met else RequirementStatus.UNMET,
            "SET_MATCHED" if met else "SET_NOT_MATCHED",
            facts={node.fact_path.value: sorted(actual), "matches": sorted(matches)},
            expected={
                "accepted_values": node.accepted_values,
                "minimum_matches": node.minimum_matches,
            },
        )

    if isinstance(node, CourseGroupRule):
        matching_refs = sorted(
            course.course_ref
            for course in profile.course_tags
            if course.tags.intersection(node.accepted_tags)
        )
        if not profile.course_tags:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={"course_tags": []},
            )
        met = len(matching_refs) >= node.minimum_courses
        return _trace(
            node,
            RequirementStatus.MET if met else RequirementStatus.UNMET,
            "COURSE_GROUP_MET" if met else "COURSE_GROUP_UNMET",
            facts={"matching_course_refs": matching_refs},
            expected={
                "accepted_tags": node.accepted_tags,
                "minimum_courses": node.minimum_courses,
            },
        )

    if isinstance(node, LanguageMinimumRule):
        results = [
            result
            for result in profile.language_results
            if result.test_type == node.test_type
        ]
        if not results:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={f"language_results.{node.test_type.value}": []},
            )
        observed: list[dict[str, Any]] = []
        incomplete = False
        total_failed = False
        component_failed = False
        for result in results:
            row = {
                "total": result.total,
                "components": result.components,
            }
            observed.append(_json_value(row))
            if node.total_min is not None and result.total is None:
                incomplete = True
                continue
            missing_components = [
                component
                for component in node.component_mins
                if result.components.get(component) is None
            ]
            if missing_components:
                incomplete = True
                continue
            total_ok = node.total_min is None or result.total >= node.total_min
            components_ok = all(
                result.components[component] >= minimum
                for component, minimum in node.component_mins.items()
            )
            if total_ok and components_ok:
                return _trace(
                    node,
                    RequirementStatus.MET,
                    "LANGUAGE_MET",
                    facts={"matching_results": observed},
                    expected={
                        "test_type": node.test_type,
                        "total_min": node.total_min,
                        "component_mins": node.component_mins,
                    },
                )
            total_failed = total_failed or not total_ok
            component_failed = component_failed or not components_ok
        if incomplete:
            status = RequirementStatus.MISSING_INFORMATION
            reason = "LANGUAGE_COMPONENT_MISSING"
        elif total_failed:
            status = RequirementStatus.UNMET
            reason = "LANGUAGE_TOTAL_UNMET"
        else:
            status = RequirementStatus.UNMET
            reason = "LANGUAGE_COMPONENT_UNMET" if component_failed else "LANGUAGE_TOTAL_UNMET"
        return _trace(
            node,
            status,
            reason,
            facts={"matching_results": observed},
            expected={
                "test_type": node.test_type,
                "total_min": node.total_min,
                "component_mins": node.component_mins,
            },
        )

    if isinstance(node, DurationMinMonthsRule):
        value = _fact(profile, node.fact_path)
        if value is None:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={node.fact_path.value: None},
            )
        met = value >= node.minimum_months
        return _trace(
            node,
            RequirementStatus.MET if met else RequirementStatus.UNMET,
            "WORK_DURATION_MET" if met else "WORK_DURATION_UNMET",
            facts={node.fact_path.value: value},
            expected={"minimum_months": node.minimum_months},
        )

    if isinstance(node, BooleanIsRule):
        value = _fact(profile, node.fact_path)
        if value is None:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={node.fact_path.value: None},
            )
        met = value is node.expected
        return _trace(
            node,
            RequirementStatus.MET if met else RequirementStatus.UNMET,
            "BOOLEAN_MATCHED" if met else "BOOLEAN_NOT_MATCHED",
            facts={node.fact_path.value: value},
            expected={"expected": node.expected},
        )

    if isinstance(node, ManualReviewRule):
        return _trace(
            node,
            RequirementStatus.MANUAL_REVIEW,
            node.reason_code,
        )

    if isinstance(node, CaseRule):
        selector = _fact(profile, FactPath(node.selector_path))
        if selector is None:
            return _trace(
                node,
                RequirementStatus.MISSING_INFORMATION,
                "FACT_MISSING",
                facts={FactPath(node.selector_path).value: None},
            )
        selector_value = str(_json_value(selector))
        selected = node.cases.get(selector_value)
        if selected is None:
            selected = node.default
        if selected is None:
            return _trace(
                node,
                RequirementStatus.MANUAL_REVIEW,
                "CASE_NOT_COVERED",
                facts={FactPath(node.selector_path).value: selector_value},
            )
        child = evaluate_node(profile, selected)
        return _trace(
            node,
            child.status,
            "CASE_SELECTED",
            facts={FactPath(node.selector_path).value: selector_value},
            expected={"selected_node_id": selected.node_id},
            children=[child],
        )

    raise TypeError(f"Unsupported rule node: {type(node).__name__}")


def _walk_traces(trace: NodeTrace):
    yield trace
    for child in trace.children:
        yield from _walk_traces(child)


def _requirement_result(
    profile: ApplicantEligibilityInput, requirement: RequirementFixture
) -> RequirementResult:
    if requirement.applicability is not None:
        applicability = evaluate_node(profile, requirement.applicability)
        if applicability.status == RequirementStatus.UNMET:
            trace = NodeTrace(
                node_id=requirement.applicability.node_id,
                operator="applicability",
                status=RequirementStatus.NOT_APPLICABLE,
                reason_code="NOT_APPLICABLE",
                facts_read=applicability.facts_read,
                expected=applicability.expected,
                children=[applicability],
            )
            status = RequirementStatus.NOT_APPLICABLE
        elif applicability.status in {
            RequirementStatus.MISSING_INFORMATION,
            RequirementStatus.MANUAL_REVIEW,
        }:
            trace = applicability
            status = applicability.status
        else:
            trace = evaluate_node(profile, requirement.rule)
            status = trace.status
    else:
        trace = evaluate_node(profile, requirement.rule)
        status = trace.status
    return RequirementResult(
        requirement_id=requirement.requirement_id,
        requirement_type=requirement.requirement_type,
        is_hard=requirement.is_hard,
        status=status,
        reason_code=trace.reason_code,
        evidence_fixture_ids=requirement.evidence_fixture_ids,
        trace=trace,
    )


def _overall_status(results: list[RequirementResult]) -> RequirementStatus:
    active = [
        result.status
        for result in results
        if result.is_hard and result.status != RequirementStatus.NOT_APPLICABLE
    ]
    if not active:
        return RequirementStatus.NOT_APPLICABLE
    if RequirementStatus.UNMET in active:
        return RequirementStatus.UNMET
    if RequirementStatus.MANUAL_REVIEW in active:
        return RequirementStatus.MANUAL_REVIEW
    if RequirementStatus.MISSING_INFORMATION in active:
        return RequirementStatus.MISSING_INFORMATION
    return RequirementStatus.MET


class RequirementEngine:
    version = ENGINE_VERSION

    def evaluate(
        self,
        profile: ApplicantEligibilityInput,
        rule_set: RequirementRuleSet,
    ) -> RequirementEvaluation:
        profile_hash = content_hash(profile)
        ruleset_hash = content_hash(rule_set)
        evaluation_id = hashlib.sha256(
            f"{profile_hash}{ruleset_hash}{self.version}".encode("utf-8")
        ).hexdigest()
        results = [
            _requirement_result(profile, requirement)
            for requirement in rule_set.requirements
        ]
        missing_fields = sorted(
            {
                field
                for result in results
                for trace in _walk_traces(result.trace)
                if trace.status == RequirementStatus.MISSING_INFORMATION
                for field, value in trace.facts_read.items()
                if value is None or value == []
            }
        )
        manual_reasons = sorted(
            {
                trace.reason_code
                for result in results
                for trace in _walk_traces(result.trace)
                if trace.status == RequirementStatus.MANUAL_REVIEW
            }
        )
        return RequirementEvaluation(
            schema_version="requirement_evaluation.v1",
            evaluation_id=evaluation_id,
            engine_version=self.version,
            profile_ref=profile.profile_ref,
            profile_hash=profile_hash,
            ruleset_id=rule_set.ruleset_id,
            ruleset_version=rule_set.ruleset_version,
            ruleset_hash=ruleset_hash,
            overall_hard_requirement_status=_overall_status(results),
            requirement_results=results,
            missing_fields=missing_fields,
            manual_review_reasons=manual_reasons,
        )
