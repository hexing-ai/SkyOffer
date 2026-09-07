from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "golden"
    / "requirement_engine_v1.candidate.jsonl"
)
GOLD_SET_VERSION = "requirement_engine_gold.candidate.v0.1.0"
CATEGORIES = [
    "degree",
    "academic",
    "subject",
    "course",
    "language",
    "work_experience",
    "material",
]


def base_profile(suffix: str) -> dict:
    return {
        "schema_version": "applicant_eligibility_input.v1",
        "profile_ref": f"profile.gold.{suffix}",
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
            {"course_ref": "course.ml", "tags": ["machine_learning"]},
        ],
        "language_results": [
            {
                "test_type": "ielts",
                "total": "7.0",
                "components": {
                    "listening": "7.0",
                    "reading": "7.0",
                    "writing": "6.5",
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


def ruleset(suffix: str, category: str, rule: dict, applicability: dict | None = None) -> dict:
    return {
        "schema_version": "requirement_rule_set.v1",
        "ruleset_id": f"ruleset.gold.{suffix}",
        "ruleset_version": "1.0.0",
        "engine_contract_version": "requirement_engine.v1",
        "synthetic_program_ref": f"program.gold.{suffix}",
        "requirements": [
            {
                "requirement_id": f"requirement.gold.{suffix}",
                "requirement_type": category,
                "is_hard": True,
                "applicability": applicability,
                "rule": rule,
                "evidence_fixture_ids": [f"evidence.gold.{suffix}"],
                "display_text": "待产品负责人复核的合成门槛规则",
            }
        ],
    }


def leaf(kind: str, suffix: str, **values) -> dict:
    return {"node_id": f"node.{kind}.{suffix}", **values}


def met_pattern(index: int, suffix: str, profile: dict) -> tuple[dict, str, str]:
    pattern = index % 10
    variation = index // 10
    if pattern == 0:
        if variation == 1:
            return leaf("enum", suffix, operator="enum_in", fact_path="degree_status", allowed_values=["in_progress", "awarded"]), "leaf", "ENUM_ALLOWED"
        if variation == 2:
            return leaf("enum", suffix, operator="enum_in", fact_path="applicant_region", allowed_values=["china_mainland"]), "leaf", "ENUM_ALLOWED"
        return leaf("enum", suffix, operator="enum_in", fact_path="degree_level", allowed_values=["bachelor"]), "leaf", "ENUM_ALLOWED"
    if pattern == 1:
        if variation == 1:
            profile["academic_record"]["value"] = "80"
            return leaf("numeric", suffix, operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100"), "leaf", "VALUE_AT_OR_ABOVE_MIN"
        if variation == 2:
            return leaf("numeric", suffix, operator="numeric_max", fact_path="graduation_year", maximum=2027), "leaf", "VALUE_AT_OR_BELOW_MAX"
        profile["academic_record"]["value"] = str(80 + index / 100)
        return leaf("numeric", suffix, operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100"), "leaf", "VALUE_AT_OR_ABOVE_MIN"
    if pattern == 2:
        if variation == 1:
            profile["degree_subject_tags"] = ["automation", "electronic_engineering"]
            return leaf("set", suffix, operator="set_intersects", fact_path="degree_subject_tags", accepted_values=["automation", "electronic_engineering"], minimum_matches=2), "leaf", "SET_MATCHED"
        if variation == 2:
            return leaf("set", suffix, operator="set_intersects", fact_path="institution_tags", accepted_values=["china_mainland_recognized"], minimum_matches=1), "leaf", "SET_MATCHED"
        return leaf("set", suffix, operator="set_intersects", fact_path="degree_subject_tags", accepted_values=["automation", "computer_science"], minimum_matches=1), "leaf", "SET_MATCHED"
    if pattern == 3:
        if variation == 1:
            return leaf("course", suffix, operator="course_group", accepted_tags=["mathematics"], minimum_courses=1), "leaf", "COURSE_GROUP_MET"
        if variation == 2:
            return leaf("course", suffix, operator="course_group", accepted_tags=["mathematics", "programming", "machine_learning"], minimum_courses=3), "leaf", "COURSE_GROUP_MET"
        return leaf("course", suffix, operator="course_group", accepted_tags=["programming", "machine_learning"], minimum_courses=2), "leaf", "COURSE_GROUP_MET"
    if pattern == 4:
        if variation == 1:
            profile["language_results"] = [{"test_type": "toefl", "total": "95", "components": {"writing": "22"}}]
            return leaf("language", suffix, operator="language_minimum", test_type="toefl", total_min="90", component_mins={"writing": "21"}), "leaf", "LANGUAGE_MET"
        if variation == 2:
            profile["language_results"] = [{"test_type": "pte", "total": "70", "components": {"writing": "65"}}]
            return leaf("language", suffix, operator="language_minimum", test_type="pte", total_min="65", component_mins={"writing": "60"}), "leaf", "LANGUAGE_MET"
        return leaf("language", suffix, operator="language_minimum", test_type="ielts", total_min="6.5", component_mins={"writing": "6.0"}), "leaf", "LANGUAGE_MET"
    if pattern == 5:
        if variation == 1:
            return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=6), "leaf", "WORK_DURATION_MET"
        if variation == 2:
            return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=0), "leaf", "WORK_DURATION_MET"
        return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=12), "leaf", "WORK_DURATION_MET"
    if pattern == 6:
        if variation == 1:
            return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.recommendation_letters", expected=True), "leaf", "BOOLEAN_MATCHED"
        if variation == 2:
            profile["materials"]["portfolio"] = False
            return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.portfolio", expected=False), "leaf", "BOOLEAN_MATCHED"
        return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.portfolio", expected=True), "leaf", "BOOLEAN_MATCHED"
    if pattern == 7:
        if variation == 1:
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_status", allowed_values=["in_progress"]), leaf("numeric", suffix + "b", operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100")]
            return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
        if variation == 2:
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_level", allowed_values=["bachelor"]), leaf("numeric", suffix + "b", operator="numeric_min", fact_path="graduation_year", minimum=2027), leaf("boolean", suffix + "c", operator="boolean_is", fact_path="materials.portfolio", expected=True)]
            return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
        children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_level", allowed_values=["bachelor"]), leaf("numeric", suffix + "b", operator="numeric_min", fact_path="graduation_year", minimum=2027)]
        return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
    if pattern == 8:
        if variation == 1:
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_level", allowed_values=["master"]), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.portfolio", expected=True)]
            return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
        if variation == 2:
            children = [leaf("manual", suffix + "a", operator="manual_review"), leaf("numeric", suffix + "b", operator="numeric_min", fact_path="graduation_year", minimum=2027)]
            return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
        children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2027), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.interview", expected=True)]
        return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
    if variation == 1:
        profile["applicant_region"] = "other"
        branch = leaf("manual", suffix + "a", operator="manual_review")
        default = leaf("numeric", suffix + "b", operator="numeric_min", fact_path="graduation_year", minimum=2027)
        return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"china_mainland": branch}, default=default), "case", "CASE_SELECTED"
    if variation == 2:
        profile["applicant_region"] = "hong_kong"
        branch = leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2027)
        return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"hong_kong": branch}), "case", "CASE_SELECTED"
    branch = leaf("numeric", suffix + "a", operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100")
    default = leaf("manual", suffix + "b", operator="manual_review")
    return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"china_mainland": branch}, default=default), "case", "CASE_SELECTED"


def unmet_pattern(index: int, suffix: str, profile: dict) -> tuple[dict, str, str]:
    pattern = index % 10
    variation = index // 10
    if pattern == 0:
        if variation == 1:
            return leaf("enum", suffix, operator="enum_in", fact_path="degree_status", allowed_values=["awarded"]), "leaf", "ENUM_NOT_ALLOWED"
        if variation == 2:
            return leaf("enum", suffix, operator="enum_in", fact_path="applicant_region", allowed_values=["hong_kong"]), "leaf", "ENUM_NOT_ALLOWED"
        return leaf("enum", suffix, operator="enum_in", fact_path="degree_level", allowed_values=["master"]), "leaf", "ENUM_NOT_ALLOWED"
    if pattern == 1:
        if variation == 1:
            profile["academic_record"]["value"] = "79.99"
            return leaf("numeric", suffix, operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100"), "leaf", "VALUE_BELOW_MIN"
        if variation == 2:
            profile["graduation_year"] = 2028
            return leaf("numeric", suffix, operator="numeric_max", fact_path="graduation_year", maximum=2027), "leaf", "VALUE_ABOVE_MAX"
        profile["academic_record"]["value"] = str(79 - index / 100)
        return leaf("numeric", suffix, operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100"), "leaf", "VALUE_BELOW_MIN"
    if pattern == 2:
        if variation == 1:
            return leaf("set", suffix, operator="set_intersects", fact_path="institution_tags", accepted_values=["china_mainland_priority"], minimum_matches=1), "leaf", "SET_NOT_MATCHED"
        if variation == 2:
            return leaf("set", suffix, operator="set_intersects", fact_path="degree_subject_tags", accepted_values=["aerospace_engineering", "mechanical_engineering"], minimum_matches=1), "leaf", "SET_NOT_MATCHED"
        return leaf("set", suffix, operator="set_intersects", fact_path="degree_subject_tags", accepted_values=["computer_science", "artificial_intelligence"], minimum_matches=1), "leaf", "SET_NOT_MATCHED"
    if pattern == 3:
        if variation == 1:
            return leaf("course", suffix, operator="course_group", accepted_tags=["control", "aerospace"], minimum_courses=2), "leaf", "COURSE_GROUP_UNMET"
        if variation == 2:
            return leaf("course", suffix, operator="course_group", accepted_tags=["mathematics", "programming", "machine_learning"], minimum_courses=4), "leaf", "COURSE_GROUP_UNMET"
        return leaf("course", suffix, operator="course_group", accepted_tags=["databases", "data_structures"], minimum_courses=2), "leaf", "COURSE_GROUP_UNMET"
    if pattern == 4:
        if variation == 1:
            profile["language_results"] = [{"test_type": "toefl", "total": "85", "components": {"writing": "22"}}]
            return leaf("language", suffix, operator="language_minimum", test_type="toefl", total_min="90", component_mins={"writing": "21"}), "leaf", "LANGUAGE_TOTAL_UNMET"
        if variation == 2:
            profile["language_results"] = [{"test_type": "pte", "total": "70", "components": {"writing": "50"}}]
            return leaf("language", suffix, operator="language_minimum", test_type="pte", total_min="65", component_mins={"writing": "60"}), "leaf", "LANGUAGE_COMPONENT_UNMET"
        return leaf("language", suffix, operator="language_minimum", test_type="ielts", total_min="7.5", component_mins={"writing": "6.0"}), "leaf", "LANGUAGE_TOTAL_UNMET"
    if pattern == 5:
        if variation == 1:
            return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=13), "leaf", "WORK_DURATION_UNMET"
        if variation == 2:
            return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=120), "leaf", "WORK_DURATION_UNMET"
        return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=24), "leaf", "WORK_DURATION_UNMET"
    if pattern == 6:
        if variation == 1:
            return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.recommendation_letters", expected=False), "leaf", "BOOLEAN_NOT_MATCHED"
        if variation == 2:
            profile["materials"]["portfolio"] = False
            return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.portfolio", expected=True), "leaf", "BOOLEAN_NOT_MATCHED"
        return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.portfolio", expected=False), "leaf", "BOOLEAN_NOT_MATCHED"
    if pattern == 7:
        if variation == 1:
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_status", allowed_values=["awarded"]), leaf("numeric", suffix + "b", operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100")]
            return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
        if variation == 2:
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_level", allowed_values=["bachelor"]), leaf("numeric", suffix + "b", operator="numeric_min", fact_path="graduation_year", minimum=2030), leaf("boolean", suffix + "c", operator="boolean_is", fact_path="materials.portfolio", expected=True)]
            return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
        children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2030), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.interview", expected=True)]
        return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
    if pattern == 8:
        if variation == 1:
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_level", allowed_values=["master"]), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.portfolio", expected=False)]
            return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
        if variation == 2:
            children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2030), leaf("duration", suffix + "b", operator="duration_min_months", fact_path="work_experience_months", minimum_months=24)]
            return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
        children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2030), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.portfolio", expected=False)]
        return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
    if variation == 1:
        profile["applicant_region"] = "other"
        branch = leaf("manual", suffix + "a", operator="manual_review")
        default = leaf("numeric", suffix + "b", operator="numeric_min", fact_path="academic_record.value", minimum="90", scale="100")
        return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"china_mainland": branch}, default=default), "case", "CASE_SELECTED"
    if variation == 2:
        profile["applicant_region"] = "hong_kong"
        branch = leaf("numeric", suffix + "a", operator="numeric_max", fact_path="graduation_year", maximum=2026)
        return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"hong_kong": branch}), "case", "CASE_SELECTED"
    branch = leaf("numeric", suffix + "a", operator="numeric_min", fact_path="academic_record.value", minimum="90", scale="100")
    return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"china_mainland": branch}), "case", "CASE_SELECTED"


def missing_pattern(index: int, suffix: str, profile: dict) -> tuple[dict, str, str]:
    pattern = index % 10
    variation = index // 10
    if pattern == 0:
        if variation == 1:
            profile["degree_status"] = None
            return leaf("enum", suffix, operator="enum_in", fact_path="degree_status", allowed_values=["in_progress", "awarded"]), "leaf", "FACT_MISSING"
        if variation == 2:
            profile["applicant_region"] = None
            return leaf("enum", suffix, operator="enum_in", fact_path="applicant_region", allowed_values=["china_mainland"]), "leaf", "FACT_MISSING"
        profile["degree_level"] = None
        return leaf("enum", suffix, operator="enum_in", fact_path="degree_level", allowed_values=["bachelor"]), "leaf", "FACT_MISSING"
    if pattern == 1:
        if variation == 1:
            profile["graduation_year"] = None
            return leaf("numeric", suffix, operator="numeric_min", fact_path="graduation_year", minimum=2027), "leaf", "FACT_MISSING"
        if variation == 2:
            profile["work_experience_months"] = None
            return leaf("numeric", suffix, operator="numeric_min", fact_path="work_experience_months", minimum=12), "leaf", "FACT_MISSING"
        profile["academic_record"] = None
        return leaf("numeric", suffix, operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100"), "leaf", "FACT_MISSING"
    if pattern == 2:
        if variation == 1:
            profile["institution_tags"] = []
            return leaf("set", suffix, operator="set_intersects", fact_path="institution_tags", accepted_values=["china_mainland_recognized"], minimum_matches=1), "leaf", "FACT_MISSING"
        if variation == 2:
            profile["institution_tags"] = []
            return leaf("set", suffix, operator="set_intersects", fact_path="institution_tags", accepted_values=["china_mainland_priority"], minimum_matches=1), "leaf", "FACT_MISSING"
        profile["degree_subject_tags"] = []
        return leaf("set", suffix, operator="set_intersects", fact_path="degree_subject_tags", accepted_values=["automation"], minimum_matches=1), "leaf", "FACT_MISSING"
    if pattern == 3:
        profile["course_tags"] = []
        if variation == 1:
            return leaf("course", suffix, operator="course_group", accepted_tags=["control"], minimum_courses=1), "leaf", "FACT_MISSING"
        if variation == 2:
            return leaf("course", suffix, operator="course_group", accepted_tags=["aerospace"], minimum_courses=1), "leaf", "FACT_MISSING"
        return leaf("course", suffix, operator="course_group", accepted_tags=["programming"], minimum_courses=1), "leaf", "FACT_MISSING"
    if pattern == 4:
        if variation == 1:
            profile["language_results"] = [{"test_type": "ielts", "total": "7.0", "components": {"listening": "7.0"}}]
            return leaf("language", suffix, operator="language_minimum", test_type="ielts", total_min="6.5", component_mins={"writing": "6.0"}), "leaf", "LANGUAGE_COMPONENT_MISSING"
        if variation == 2:
            profile["language_results"] = []
            return leaf("language", suffix, operator="language_minimum", test_type="toefl", total_min="90", component_mins={"writing": "21"}), "leaf", "FACT_MISSING"
        profile["language_results"] = []
        return leaf("language", suffix, operator="language_minimum", test_type="ielts", total_min="6.5", component_mins={}), "leaf", "FACT_MISSING"
    if pattern == 5:
        profile["work_experience_months"] = None
        if variation == 1:
            return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=6), "leaf", "FACT_MISSING"
        if variation == 2:
            return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=24), "leaf", "FACT_MISSING"
        return leaf("duration", suffix, operator="duration_min_months", fact_path="work_experience_months", minimum_months=12), "leaf", "FACT_MISSING"
    if pattern == 6:
        if variation == 1:
            profile["materials"]["portfolio"] = None
            return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.portfolio", expected=True), "leaf", "FACT_MISSING"
        if variation == 2:
            profile["materials"]["recommendation_letters"] = None
            return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.recommendation_letters", expected=True), "leaf", "FACT_MISSING"
        profile["materials"]["interview"] = None
        return leaf("boolean", suffix, operator="boolean_is", fact_path="materials.interview", expected=True), "leaf", "FACT_MISSING"
    if pattern == 7:
        if variation == 1:
            profile["materials"]["portfolio"] = None
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_status", allowed_values=["in_progress"]), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.portfolio", expected=True)]
            return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
        if variation == 2:
            profile["language_results"] = []
            children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2027), leaf("language", suffix + "b", operator="language_minimum", test_type="toefl", total_min="90", component_mins={})]
            return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
        children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2027), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.interview", expected=True)]
        return leaf("all", suffix, operator="all", children=children), "all", "ALL_AGGREGATED"
    if pattern == 8:
        if variation == 1:
            profile["materials"]["portfolio"] = None
            children = [leaf("enum", suffix + "a", operator="enum_in", fact_path="degree_level", allowed_values=["master"]), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.portfolio", expected=True)]
            return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
        if variation == 2:
            profile["language_results"] = []
            children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2030), leaf("language", suffix + "b", operator="language_minimum", test_type="toefl", total_min="90", component_mins={})]
            return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
        children = [leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2030), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.interview", expected=True)]
        return leaf("any", suffix, operator="any", children=children), "any", "ANY_AGGREGATED"
    profile["applicant_region"] = None
    branch = leaf("manual", suffix + "a", operator="manual_review")
    return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"china_mainland": branch}), "case", "FACT_MISSING"


def manual_pattern(index: int, suffix: str, profile: dict) -> tuple[dict, dict | None, str, str]:
    pattern = index % 10
    variation = index // 10
    if pattern == 0:
        return leaf("manual", suffix, operator="manual_review"), None, "leaf", "OFFICIAL_RULE_AMBIGUOUS"
    if pattern == 1:
        scales = [("3.4", "4"), ("8", "10"), ("4.5", "5")]
        value, scale = scales[variation]
        profile["academic_record"] = {"value": value, "scale": scale}
        return leaf("numeric", suffix, operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100"), None, "leaf", "SCALE_MISMATCH"
    if pattern == 2:
        profile["applicant_region"] = ["other", "hong_kong", "other"][variation]
        branch = leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2027)
        return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"china_mainland": branch}), None, "case", "CASE_NOT_COVERED"
    if pattern == 3:
        second = (
            leaf("numeric", suffix + "b", operator="numeric_min", fact_path="graduation_year", minimum=2027)
            if variation == 0
            else leaf("numeric", suffix + "b", operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100")
        )
        children = [leaf("manual", suffix + "a", operator="manual_review"), second]
        return leaf("all", suffix, operator="all", children=children), None, "all", "ALL_AGGREGATED"
    if pattern == 4:
        second = (
            leaf("numeric", suffix + "b", operator="numeric_min", fact_path="graduation_year", minimum=2030)
            if variation == 0
            else leaf("duration", suffix + "b", operator="duration_min_months", fact_path="work_experience_months", minimum_months=24)
        )
        children = [leaf("manual", suffix + "a", operator="manual_review"), second]
        return leaf("any", suffix, operator="any", children=children), None, "any", "ANY_AGGREGATED"
    if pattern == 5:
        applicability = leaf("manual", suffix + "app", operator="manual_review")
        return leaf("numeric", suffix, operator="numeric_min", fact_path="graduation_year", minimum=2027), applicability, "applicability", "OFFICIAL_RULE_AMBIGUOUS"
    if pattern == 6:
        scales = [("4.5", "5"), ("2.8", "4"), ("7.5", "10")]
        value, scale = scales[variation]
        profile["academic_record"] = {"value": value, "scale": scale}
        return leaf("numeric", suffix, operator="numeric_min", fact_path="academic_record.value", minimum="80", scale="100"), None, "leaf", "SCALE_MISMATCH"
    if pattern == 7:
        children = [leaf("manual", suffix + "a", operator="manual_review"), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.interview", expected=True)]
        return leaf("all", suffix, operator="all", children=children), None, "all", "ALL_AGGREGATED"
    if pattern == 8:
        children = [leaf("manual", suffix + "a", operator="manual_review"), leaf("boolean", suffix + "b", operator="boolean_is", fact_path="materials.interview", expected=True)]
        return leaf("any", suffix, operator="any", children=children), None, "any", "ANY_AGGREGATED"
    profile["applicant_region"] = "other"
    branch = leaf("numeric", suffix + "a", operator="numeric_min", fact_path="graduation_year", minimum=2027)
    default = leaf("manual", suffix + "b", operator="manual_review")
    return leaf("case", suffix, operator="case", selector_path="applicant_region", cases={"china_mainland": branch}, default=default), None, "case", "CASE_SELECTED"


def not_applicable_pattern(index: int, suffix: str, profile: dict) -> tuple[dict, dict, str, str]:
    pattern = index % 10
    variation = index // 10
    rule = leaf("manual", suffix, operator="manual_review")

    if pattern == 0:
        allowed_regions = [["hong_kong"], ["other"], ["hong_kong", "other"]]
        applicability = leaf(
            "enum",
            suffix + "app",
            operator="enum_in",
            fact_path="applicant_region",
            allowed_values=allowed_regions[variation],
        )
    elif pattern == 1:
        allowed_levels = [["master"], ["other"], ["master", "other"]]
        applicability = leaf(
            "enum",
            suffix + "app",
            operator="enum_in",
            fact_path="degree_level",
            allowed_values=allowed_levels[variation],
        )
    elif pattern == 2:
        if variation == 1:
            profile["degree_status"] = "awarded"
        allowed_statuses = [["awarded"], ["in_progress"], ["awarded"]]
        applicability = leaf(
            "enum",
            suffix + "app",
            operator="enum_in",
            fact_path="degree_status",
            allowed_values=allowed_statuses[variation],
        )
    elif pattern == 3:
        if variation == 0:
            applicability = leaf("numeric", suffix + "app", operator="numeric_min", fact_path="graduation_year", minimum=2030)
        elif variation == 1:
            applicability = leaf("numeric", suffix + "app", operator="numeric_max", fact_path="graduation_year", maximum=2025)
        else:
            applicability = leaf("numeric", suffix + "app", operator="numeric_min", fact_path="academic_record.value", minimum="85", scale="100")
    elif pattern == 4:
        accepted_subjects = [["aerospace_engineering"], ["computer_science"], ["mechanical_engineering"]]
        applicability = leaf(
            "set",
            suffix + "app",
            operator="set_intersects",
            fact_path="degree_subject_tags",
            accepted_values=accepted_subjects[variation],
            minimum_matches=1,
        )
    elif pattern == 5:
        accepted_courses = [["aerospace"], ["data_structures"], ["control"]]
        applicability = leaf(
            "course",
            suffix + "app",
            operator="course_group",
            accepted_tags=accepted_courses[variation],
            minimum_courses=1,
        )
    elif pattern == 6:
        minimum_months = [24, 18, 36]
        applicability = leaf(
            "duration",
            suffix + "app",
            operator="duration_min_months",
            fact_path="work_experience_months",
            minimum_months=minimum_months[variation],
        )
    elif pattern == 7:
        fact_paths = ["materials.portfolio", "materials.recommendation_letters", "materials.portfolio"]
        expected_values = [False, False, True]
        if variation == 2:
            profile["materials"]["portfolio"] = False
        applicability = leaf(
            "boolean",
            suffix + "app",
            operator="boolean_is",
            fact_path=fact_paths[variation],
            expected=expected_values[variation],
        )
    elif pattern == 8:
        unmet_children = [
            leaf("enum", suffix + "appb", operator="enum_in", fact_path="degree_level", allowed_values=["master"]),
            leaf("numeric", suffix + "appb", operator="numeric_min", fact_path="graduation_year", minimum=2030),
            leaf("duration", suffix + "appb", operator="duration_min_months", fact_path="work_experience_months", minimum_months=24),
        ]
        applicability = leaf(
            "all",
            suffix + "app",
            operator="all",
            children=[
                leaf("enum", suffix + "appa", operator="enum_in", fact_path="applicant_region", allowed_values=["china_mainland"]),
                unmet_children[variation],
            ],
        )
    else:
        second_unmet_children = [
            leaf("enum", suffix + "appb", operator="enum_in", fact_path="degree_status", allowed_values=["awarded"]),
            leaf("set", suffix + "appb", operator="set_intersects", fact_path="degree_subject_tags", accepted_values=["computer_science"], minimum_matches=1),
            leaf("course", suffix + "appb", operator="course_group", accepted_tags=["aerospace"], minimum_courses=1),
        ]
        applicability = leaf(
            "any",
            suffix + "app",
            operator="any",
            children=[
                leaf("enum", suffix + "appa", operator="enum_in", fact_path="degree_level", allowed_values=["master"]),
                second_unmet_children[variation],
            ],
        )

    return rule, applicability, "applicability", "NOT_APPLICABLE"


def build_cases() -> list[dict]:
    cases: list[dict] = []
    for status in ("met", "unmet", "missing_information", "manual_review", "not_applicable"):
        for index in range(30):
            suffix = f"{status.replace('_', '')}.{index:03d}"
            candidate = base_profile(suffix)
            category = CATEGORIES[index % len(CATEGORIES)]
            applicability = None
            if status == "met":
                rule, structure, reason = met_pattern(index, suffix, candidate)
            elif status == "unmet":
                rule, structure, reason = unmet_pattern(index, suffix, candidate)
            elif status == "missing_information":
                rule, structure, reason = missing_pattern(index, suffix, candidate)
            elif status == "manual_review":
                rule, applicability, structure, reason = manual_pattern(index, suffix, candidate)
            else:
                rule, applicability, structure, reason = not_applicable_pattern(index, suffix, candidate)
            cases.append(
                {
                    "case_id": f"gold.{status}.{index:03d}",
                    "gold_set_version": GOLD_SET_VERSION,
                    "review_status": "pending_product_owner_review",
                    "reviewer_role": None,
                    "review_date": None,
                    "category": category,
                    "structure": structure,
                    "profile": candidate,
                    "rule_set": ruleset(suffix, category, rule, applicability),
                    "expected_status": status,
                    "expected_reason_code": reason,
                    "review_note_zh": f"候选案例：预期五态为 {status}；需产品负责人独立复核。",
                }
            )
    return cases


def main() -> None:
    cases = build_cases()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(case, ensure_ascii=False, sort_keys=True) for case in cases)
    OUTPUT.write_text(body + "\n", encoding="utf-8")
    print(f"generated {len(cases)} pending-review candidates at {OUTPUT}")


if __name__ == "__main__":
    main()
