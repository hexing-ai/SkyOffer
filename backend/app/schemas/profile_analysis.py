from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ShortText = Annotated[str, Field(min_length=1, max_length=120)]
DescriptionText = Annotated[str, Field(min_length=1, max_length=800)]

DISCLAIMER = (
    "本结果仅分析你提供的申请资料，未使用已核验院校项目数据，也未进行项目门槛、"
    "录取概率或录取承诺判断。"
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EducationStatus(StrEnum):
    UNDERGRADUATE = "undergraduate"
    GRADUATED = "graduated"
    OTHER = "other"


class TargetRegion(StrEnum):
    HONG_KONG = "hong_kong"
    UNITED_KINGDOM = "united_kingdom"


class TargetDirection(StrEnum):
    COMPUTER_SCIENCE = "computer_science"
    ARTIFICIAL_INTELLIGENCE = "artificial_intelligence"
    AEROSPACE_ENGINEERING = "aerospace_engineering"
    LOW_ALTITUDE_ECONOMY = "low_altitude_economy"


class ExperienceType(StrEnum):
    INTERNSHIP = "internship"
    RESEARCH = "research"
    PROJECT = "project"
    PAPER = "paper"
    COMPETITION = "competition"
    WORK = "work"
    OTHER = "other"


class LanguageScore(StrictModel):
    test_type: Annotated[str, Field(min_length=1, max_length=30)]
    total_score: Annotated[float, Field(ge=0, le=1000)]
    component_scores: dict[Annotated[str, Field(max_length=30)], float] = Field(
        default_factory=dict, max_length=8
    )
    test_date: date | None = None


class Experience(StrictModel):
    type: ExperienceType
    title: ShortText
    description: DescriptionText


class ApplicantAnalysisInput(StrictModel):
    schema_version: Literal["applicant_analysis_input.v1"]
    request_language: Literal["zh-CN"] = "zh-CN"
    education_status: EducationStatus
    graduation_year: Annotated[int, Field(ge=2000, le=2035)]
    undergraduate_institution: ShortText
    undergraduate_major: ShortText
    degree_type: ShortText
    grading_scale: Annotated[float, Field(gt=0, le=1000)]
    grade_value: Annotated[float, Field(ge=0, le=1000)]
    core_courses: Annotated[list[ShortText], Field(default_factory=list, max_length=30)]
    language_scores: Annotated[list[LanguageScore], Field(default_factory=list, max_length=5)]
    experiences: Annotated[list[Experience], Field(default_factory=list, max_length=15)]
    target_regions: Annotated[list[TargetRegion], Field(min_length=1, max_length=2)]
    target_directions: Annotated[list[TargetDirection], Field(min_length=1, max_length=4)]
    career_goal: Annotated[str | None, Field(default=None, max_length=500)]
    budget_note: Annotated[str | None, Field(default=None, max_length=200)]

    @model_validator(mode="after")
    def validate_grading_scale(self) -> "ApplicantAnalysisInput":
        if self.grade_value > self.grading_scale:
            raise ValueError("grade_value cannot exceed grading_scale")
        if len(set(self.target_regions)) != len(self.target_regions):
            raise ValueError("target_regions cannot contain duplicates")
        if len(set(self.target_directions)) != len(self.target_directions):
            raise ValueError("target_directions cannot contain duplicates")
        return self


class ProfileSummary(StrictModel):
    education: Annotated[str, Field(min_length=1, max_length=300)]
    academic_metrics_raw: Annotated[str, Field(min_length=1, max_length=160)]
    target_summary: Annotated[str, Field(min_length=1, max_length=300)]


class DirectionEvidence(StrictModel):
    direction: TargetDirection
    signals: Annotated[list[DescriptionText], Field(max_length=8)]
    gaps: Annotated[list[DescriptionText], Field(max_length=8)]
    input_evidence_refs: Annotated[list[ShortText], Field(max_length=20)]


class MissingInformation(StrictModel):
    field: ShortText
    why_it_matters: DescriptionText
    requested_input: DescriptionText


class ConsistencyFlag(StrictModel):
    field_refs: Annotated[list[ShortText], Field(min_length=1, max_length=8)]
    issue: DescriptionText
    clarification_needed: DescriptionText


class ModelAnalysisPayload(StrictModel):
    schema_version: Literal["applicant_analysis_output.v1"]
    analysis_scope: Literal["profile_only"]
    profile_summary: ProfileSummary
    direction_evidence: Annotated[list[DirectionEvidence], Field(min_length=1, max_length=4)]
    missing_information: Annotated[list[MissingInformation], Field(max_length=15)]
    consistency_flags: Annotated[list[ConsistencyFlag], Field(max_length=10)]
    next_questions: Annotated[list[DescriptionText], Field(min_length=3, max_length=7)]
    limitations: Annotated[list[DescriptionText], Field(min_length=2, max_length=6)]


class AnalysisMeta(StrictModel):
    request_id: str
    prompt_version: str
    model_name: str
    generated_at: datetime
    duration_ms: int = Field(ge=0)


class ApplicantAnalysisOutput(ModelAnalysisPayload):
    disclaimer: Literal[DISCLAIMER]
    meta: AnalysisMeta


def allowed_input_evidence_refs(profile: ApplicantAnalysisInput) -> set[str]:
    refs = {
        "education_status",
        "graduation_year",
        "undergraduate_institution",
        "undergraduate_major",
        "degree_type",
        "grading_scale",
        "grade_value",
        "career_goal",
        "budget_note",
    }
    refs.update(f"core_courses[{index}]" for index in range(len(profile.core_courses)))
    for index, score in enumerate(profile.language_scores):
        refs.update(
            {
                f"language_scores[{index}]",
                f"language_scores[{index}].test_type",
                f"language_scores[{index}].total_score",
                f"language_scores[{index}].test_date",
            }
        )
        refs.update(
            f"language_scores[{index}].component_scores.{name}"
            for name in score.component_scores
        )
    for index in range(len(profile.experiences)):
        refs.update(
            {
                f"experiences[{index}]",
                f"experiences[{index}].type",
                f"experiences[{index}].title",
                f"experiences[{index}].description",
            }
        )
    refs.update(f"target_regions[{index}]" for index in range(len(profile.target_regions)))
    refs.update(
        f"target_directions[{index}]" for index in range(len(profile.target_directions))
    )
    return refs
