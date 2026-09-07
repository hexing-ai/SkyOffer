from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field

from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.requirement_rules import (
    ApplicantEligibilityInput,
    RequirementRuleSet,
)


class RequirementStatus(StrEnum):
    MET = "met"
    UNMET = "unmet"
    MISSING_INFORMATION = "missing_information"
    MANUAL_REVIEW = "manual_review"
    NOT_APPLICABLE = "not_applicable"


class NodeTrace(StrictModel):
    node_id: str
    operator: str
    status: RequirementStatus
    reason_code: str
    facts_read: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    children: list["NodeTrace"] = Field(default_factory=list)


class RequirementResult(StrictModel):
    requirement_id: str
    requirement_type: str
    is_hard: bool
    status: RequirementStatus
    reason_code: str
    evidence_fixture_ids: list[str]
    trace: NodeTrace


class RequirementEvaluation(StrictModel):
    schema_version: Literal["requirement_evaluation.v1"]
    evaluation_id: str
    engine_version: str
    profile_ref: str
    profile_hash: str
    ruleset_id: str
    ruleset_version: str
    ruleset_hash: str
    overall_hard_requirement_status: RequirementStatus
    requirement_results: list[RequirementResult]
    missing_fields: list[str]
    manual_review_reasons: list[str]


class RequirementEvaluationRequest(StrictModel):
    profile: ApplicantEligibilityInput
    rule_set: RequirementRuleSet


class RequirementEvaluationResponse(RequirementEvaluation):
    request_id: str
    duration_ms: Annotated[int, Field(ge=0)]
