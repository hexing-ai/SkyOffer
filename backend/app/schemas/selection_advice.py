from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.profile_analysis import (
    ApplicantAnalysisInput,
    DescriptionText,
    StrictModel,
)
from backend.app.schemas.historical_reference import HistoricalReferenceResult
from backend.app.schemas.requirement_evaluation import RequirementStatus
from backend.app.schemas.requirement_rules import ApplicantEligibilityInput, MaterialFacts


class InstitutionRecognition(StrEnum):
    UNKNOWN = "unknown"
    RECOGNIZED = "mainland_recognized"
    PRIORITY = "mainland_priority"


class ApplicantRuleFacts(StrictModel):
    institution_recognition: InstitutionRecognition = InstitutionRecognition.UNKNOWN
    work_experience_months: Annotated[int | None, Field(default=None, ge=0, le=1200)]
    materials: MaterialFacts = Field(default_factory=MaterialFacts)


class SelectionAdviceRequest(StrictModel):
    schema_version: Literal["selection_advice_request.v1"]
    profile: ApplicantAnalysisInput
    rule_facts: ApplicantRuleFacts = Field(default_factory=ApplicantRuleFacts)


class RecommendationTier(StrEnum):
    SPRINT = "sprint"
    TARGET = "target"
    RELATIVE_SAFE = "relative_safe"
    VERIFY = "verify"


TIER_LABELS = {
    RecommendationTier.SPRINT: "冲刺",
    RecommendationTier.TARGET: "主申",
    RecommendationTier.RELATIVE_SAFE: "相对稳妥",
    RecommendationTier.VERIFY: "待核验",
}


class OfficialCitation(StrictModel):
    evidence_id: str
    field_key: str
    url: str
    page_title: str
    excerpt: str
    source_version: str
    verified_at: datetime
    review_due_at: datetime
    freshness: Literal["fresh", "review_due", "expired", "source_unavailable"]


class FieldJudgment(StrictModel):
    field_key: str
    coverage_status: str
    status: RequirementStatus
    is_critical: bool
    is_high_risk: bool
    display_text: str
    reason_codes: list[str]
    citations: Annotated[list[OfficialCitation], Field(min_length=1, max_length=50)]


class ProgramExplanation(StrictModel):
    program_ref: str
    summary: DescriptionText
    strengths: Annotated[list[DescriptionText], Field(max_length=5)]
    risks: Annotated[list[DescriptionText], Field(max_length=5)]
    next_actions: Annotated[list[DescriptionText], Field(min_length=1, max_length=5)]


class SelectionExplanationPayload(StrictModel):
    schema_version: Literal["selection_explanations.v1"]
    items: Annotated[list[ProgramExplanation], Field(max_length=30)]


class ThresholdSummary(StrictModel):
    met: Annotated[int, Field(ge=0)]
    unmet: Annotated[int, Field(ge=0)]
    missing_information: Annotated[int, Field(ge=0)]
    manual_review: Annotated[int, Field(ge=0)]
    not_applicable: Annotated[int, Field(ge=0)]


class ProgramAdvice(StrictModel):
    program_ref: str
    program_name: str
    institution_name: str
    region: Literal["hong_kong", "united_kingdom"]
    official_program_url: str
    primary_direction: str
    secondary_directions: list[str]
    recommendation_tier: RecommendationTier
    recommendation_label: Literal["冲刺", "主申", "相对稳妥", "待核验"]
    threshold_summary: ThresholdSummary
    missing_fields: list[str]
    high_risk_field_keys: list[str]
    field_judgments: list[FieldJudgment]
    historical_reference: HistoricalReferenceResult | None = None
    explanation: ProgramExplanation

    @model_validator(mode="after")
    def tier_label_must_match(self) -> "ProgramAdvice":
        if self.recommendation_label != TIER_LABELS[self.recommendation_tier]:
            raise ValueError("recommendation label must be derived from tier")
        if self.explanation.program_ref != self.program_ref:
            raise ValueError("explanation must belong to the same Program")
        return self


class SelectionAdviceMeta(StrictModel):
    request_id: str
    dataset_id: str
    dataset_manifest_sha256: str
    model_name: str
    prompt_version: str
    generated_at: datetime
    duration_ms: Annotated[int, Field(ge=0)]


SELECTION_DISCLAIMER = (
    "分层仅表示基于当前已核验项目门槛的满足度与待核验项，不代表录取概率或录取承诺；"
    "“相对稳妥”也不等于保底。"
)


class SelectionAdviceResponse(StrictModel):
    schema_version: Literal["selection_advice_response.v1"]
    eligibility_profile: ApplicantEligibilityInput
    results: list[ProgramAdvice]
    excluded_program_count: Annotated[int, Field(ge=0)]
    empty_reason: str | None
    disclaimer: Literal[
        "分层仅表示基于当前已核验项目门槛的满足度与待核验项，不代表录取概率或录取承诺；“相对稳妥”也不等于保底。"
    ]
    meta: SelectionAdviceMeta

    @field_validator("results")
    @classmethod
    def results_must_be_unique(cls, value: list[ProgramAdvice]) -> list[ProgramAdvice]:
        refs = [item.program_ref for item in value]
        if len(refs) != len(set(refs)):
            raise ValueError("selection results must contain unique Programs")
        return value
