from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, TypeAdapter, model_validator

from backend.app.schemas.evidence import Identifier
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.requirement_rules import (
    AllRule,
    AnyRule,
    CaseRule,
    RequirementFixture,
    RuleNode,
)


AcademicYear = Annotated[str, Field(pattern=r"^20\d{2}-\d{2}$")]
ReviewNote = Annotated[str, Field(min_length=1, max_length=1000)]
ReviewedSourceIds = Annotated[list[Identifier], Field(min_length=1, max_length=50)]


class CoverageStatus(StrEnum):
    CONFIRMED = "confirmed"
    MANUAL_REVIEW = "manual_review"
    NOT_YET_PUBLISHED = "not_yet_published"
    NOT_FOUND_IN_REVIEWED_SOURCES = "not_found_in_reviewed_sources"
    NOT_APPLICABLE = "not_applicable"


class ManualReviewReasonCode(StrEnum):
    OFFICIAL_RULE_AMBIGUOUS = "OFFICIAL_RULE_AMBIGUOUS"
    OFFICIAL_RULE_NOT_PUBLISHED = "OFFICIAL_RULE_NOT_PUBLISHED"
    OFFICIAL_RULE_NOT_FOUND = "OFFICIAL_RULE_NOT_FOUND"
    OFFICIAL_RULE_REQUIRES_CASE_REVIEW = "OFFICIAL_RULE_REQUIRES_CASE_REVIEW"


class CoverageReason(StrictModel):
    reason_code: ManualReviewReasonCode
    detail: ReviewNote


def _validate_academic_year(value: str) -> None:
    start_year = int(value[:4])
    if value[-2:] != f"{(start_year + 1) % 100:02d}":
        raise ValueError("applicable_academic_year must describe consecutive years")


def _validate_coverage(
    *,
    academic_year: str,
    status: CoverageStatus,
    value: object | None,
    reason: CoverageReason | None,
    reviewed_source_ids: list[str],
) -> None:
    _validate_academic_year(academic_year)
    if len(reviewed_source_ids) != len(set(reviewed_source_ids)):
        raise ValueError("reviewed_source_ids cannot contain duplicates")
    reviewed_source_ids.sort()
    if status == CoverageStatus.CONFIRMED:
        if value is None:
            raise ValueError("confirmed coverage requires a structured value")
        if reason is not None:
            raise ValueError("confirmed coverage cannot include a reason payload")
    else:
        if value is not None:
            raise ValueError("non-confirmed coverage cannot retain a structured value")
        if reason is None:
            raise ValueError("non-confirmed coverage requires a reason payload")


class CatalogAcademicYearValue(StrictModel):
    academic_year: AcademicYear

    @model_validator(mode="after")
    def validate_year(self) -> "CatalogAcademicYearValue":
        _validate_academic_year(self.academic_year)
        return self


class CatalogDegreeTypeValue(StrictModel):
    degree_type: Literal["taught_masters"]


class CatalogDepartmentValue(StrictModel):
    department_name: Annotated[str, Field(min_length=1, max_length=300)]


class CatalogDurationValue(StrictModel):
    months: Annotated[int, Field(ge=1, le=120)]
    study_mode: Literal["full_time", "part_time", "mixed"]


class CatalogIntakeValue(StrictModel):
    intake_months: Annotated[
        list[Annotated[int, Field(ge=1, le=12)]], Field(min_length=1, max_length=12)
    ]

    @model_validator(mode="after")
    def unique_sorted_months(self) -> "CatalogIntakeValue":
        if len(self.intake_months) != len(set(self.intake_months)):
            raise ValueError("intake_months cannot contain duplicates")
        self.intake_months = sorted(self.intake_months)
        return self


class CatalogApplicationStatusValue(StrictModel):
    status: Literal["open", "closed", "not_yet_open", "rolling"]
    opens_on: date | None = None
    closes_on: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "CatalogApplicationStatusValue":
        if self.opens_on and self.closes_on and self.closes_on < self.opens_on:
            raise ValueError("closes_on cannot be before opens_on")
        return self


class _CatalogFieldBase(StrictModel):
    schema_version: Literal["program_catalog_field.v1"]
    applicable_academic_year: AcademicYear
    coverage_status: CoverageStatus
    reviewed_source_ids: ReviewedSourceIds
    review_note: ReviewNote | None = None
    reason: CoverageReason | None = None


class CatalogAcademicYearFieldV1(_CatalogFieldBase):
    field_key: Literal["catalog.academic_year"]
    value: CatalogAcademicYearValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "CatalogAcademicYearFieldV1":
        _validate_coverage(**_coverage_args(self))
        if self.value and self.value.academic_year != self.applicable_academic_year:
            raise ValueError("catalog academic year must match applicable_academic_year")
        return self


class CatalogDegreeTypeFieldV1(_CatalogFieldBase):
    field_key: Literal["catalog.degree_type"]
    value: CatalogDegreeTypeValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "CatalogDegreeTypeFieldV1":
        _validate_coverage(**_coverage_args(self))
        return self


class CatalogDepartmentFieldV1(_CatalogFieldBase):
    field_key: Literal["catalog.department"]
    value: CatalogDepartmentValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "CatalogDepartmentFieldV1":
        _validate_coverage(**_coverage_args(self))
        return self


class CatalogDurationFieldV1(_CatalogFieldBase):
    field_key: Literal["catalog.duration"]
    value: CatalogDurationValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "CatalogDurationFieldV1":
        _validate_coverage(**_coverage_args(self))
        return self


class CatalogIntakeFieldV1(_CatalogFieldBase):
    field_key: Literal["catalog.intake"]
    value: CatalogIntakeValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "CatalogIntakeFieldV1":
        _validate_coverage(**_coverage_args(self))
        return self


class CatalogApplicationStatusFieldV1(_CatalogFieldBase):
    field_key: Literal["catalog.application_status"]
    value: CatalogApplicationStatusValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "CatalogApplicationStatusFieldV1":
        _validate_coverage(**_coverage_args(self))
        return self


def _coverage_args(value: object) -> dict[str, object]:
    return {
        "academic_year": getattr(value, "applicable_academic_year"),
        "status": getattr(value, "coverage_status"),
        "value": getattr(value, "value"),
        "reason": getattr(value, "reason"),
        "reviewed_source_ids": getattr(value, "reviewed_source_ids"),
    }


ProgramCatalogFieldV1: TypeAlias = Annotated[
    CatalogAcademicYearFieldV1
    | CatalogDegreeTypeFieldV1
    | CatalogDepartmentFieldV1
    | CatalogDurationFieldV1
    | CatalogIntakeFieldV1
    | CatalogApplicationStatusFieldV1,
    Field(discriminator="field_key"),
]


RequirementFieldKey = Literal[
    "requirements.degree",
    "requirements.academic",
    "requirements.subject",
    "requirements.prerequisite_courses",
    "requirements.language",
    "requirements.work_experience",
    "requirements.materials",
]

_REQUIREMENT_TYPE_BY_FIELD = {
    "requirements.degree": "degree",
    "requirements.academic": "academic",
    "requirements.subject": "subject",
    "requirements.prerequisite_courses": "course",
    "requirements.language": "language",
    "requirements.work_experience": "work_experience",
    "requirements.materials": "material",
}


class ProgramRequirementFieldV2(StrictModel):
    schema_version: Literal["program_requirement_field.v2"]
    field_key: RequirementFieldKey
    applicable_academic_year: AcademicYear
    coverage_status: CoverageStatus
    requirements: Annotated[list[RequirementFixture], Field(max_length=100)]
    reviewed_source_ids: ReviewedSourceIds
    review_note: ReviewNote | None = None
    reason: CoverageReason | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> "ProgramRequirementFieldV2":
        _validate_academic_year(self.applicable_academic_year)
        if len(self.reviewed_source_ids) != len(set(self.reviewed_source_ids)):
            raise ValueError("reviewed_source_ids cannot contain duplicates")
        if self.coverage_status == CoverageStatus.CONFIRMED:
            if not self.requirements:
                raise ValueError("confirmed requirement coverage needs requirements")
            if self.reason is not None:
                raise ValueError("confirmed requirement coverage cannot include a reason")
        else:
            if self.requirements:
                raise ValueError("non-confirmed requirement coverage cannot retain rules")
            if self.reason is None:
                raise ValueError("non-confirmed requirement coverage requires a reason")

        expected_type = _REQUIREMENT_TYPE_BY_FIELD[self.field_key]
        requirement_ids = [item.requirement_id for item in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement_id values must be unique within a field")
        if any(item.requirement_type != expected_type for item in self.requirements):
            raise ValueError("requirement_type must match field_key")

        evidence_ids: list[str] = []
        node_ids: set[str] = set()

        def walk(node: RuleNode) -> None:
            if node.node_id in node_ids:
                raise ValueError("node_id values must be unique within a field")
            node_ids.add(node.node_id)
            if isinstance(node, (AllRule, AnyRule)):
                for child in node.children:
                    walk(child)
            elif isinstance(node, CaseRule):
                for child in node.cases.values():
                    walk(child)
                if node.default is not None:
                    walk(node.default)

        for requirement in self.requirements:
            evidence_ids.extend(requirement.evidence_fixture_ids)
            if requirement.applicability is not None:
                walk(requirement.applicability)
            walk(requirement.rule)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("requirement evidence IDs must be unique within a field")
        if not set(evidence_ids).issubset(self.reviewed_source_ids):
            raise ValueError("requirement evidence must belong to reviewed_source_ids")
        self.reviewed_source_ids = sorted(self.reviewed_source_ids)
        return self


class ProgramDirection(StrEnum):
    COMPUTER_SCIENCE = "computer_science"
    ARTIFICIAL_INTELLIGENCE = "artificial_intelligence"
    AEROSPACE_ENGINEERING = "aerospace_engineering"
    LOW_ALTITUDE_ECONOMY = "low_altitude_economy"


class LowAltitudeInclusionBasis(StrEnum):
    EXPLICIT_PROGRAM_FOCUS = "explicit_program_focus"
    CURRICULUM_BASED = "curriculum_based"


class LowAltitudeSubtag(StrEnum):
    UNMANNED_AIRCRAFT_SYSTEMS = "unmanned_aircraft_systems"
    ROBOTICS_AUTONOMOUS_SYSTEMS = "robotics_autonomous_systems"
    AVIONICS_FLIGHT_CONTROL = "avionics_flight_control"
    ADVANCED_URBAN_AIR_MOBILITY = "advanced_urban_air_mobility"
    AIR_TRAFFIC_MANAGEMENT = "air_traffic_management"
    AIRBORNE_SENSING_NAVIGATION_COMMUNICATIONS = (
        "airborne_sensing_navigation_communications"
    )
    LOW_ALTITUDE_SAFETY_SYSTEMS = "low_altitude_safety_systems"


class PrimaryDirectionValue(StrictModel):
    direction: ProgramDirection


class SecondaryDirectionsValue(StrictModel):
    directions: Annotated[list[ProgramDirection], Field(max_length=4)]

    @model_validator(mode="after")
    def unique_sorted_directions(self) -> "SecondaryDirectionsValue":
        if len(self.directions) != len(set(self.directions)):
            raise ValueError("secondary directions cannot contain duplicates")
        self.directions = sorted(self.directions, key=lambda item: item.value)
        return self


class LowAltitudeCourseEvidence(StrictModel):
    course_name: Annotated[str, Field(min_length=1, max_length=300)]
    course_type: Literal["core", "required", "elective", "unknown"]
    subtag: LowAltitudeSubtag
    evidence_id: Identifier


class LowAltitudeBasisValue(StrictModel):
    inclusion_basis: LowAltitudeInclusionBasis
    subtags: Annotated[list[LowAltitudeSubtag], Field(min_length=1, max_length=7)]
    rationale_zh: Annotated[str, Field(min_length=1, max_length=1000)]
    courses: Annotated[list[LowAltitudeCourseEvidence], Field(min_length=1, max_length=50)]
    counterexample_check_completed: Literal[True]

    @model_validator(mode="after")
    def validate_basis(self) -> "LowAltitudeBasisValue":
        if len(self.subtags) != len(set(self.subtags)):
            raise ValueError("low-altitude subtags cannot contain duplicates")
        evidence_ids = [course.evidence_id for course in self.courses]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("low-altitude course evidence IDs cannot contain duplicates")
        if not {course.subtag for course in self.courses}.issubset(self.subtags):
            raise ValueError("course subtags must be declared in subtags")
        if self.inclusion_basis == LowAltitudeInclusionBasis.CURRICULUM_BASED:
            if len(self.courses) < 2:
                raise ValueError("curriculum_based requires at least two courses")
            if not any(course.course_type in {"core", "required"} for course in self.courses):
                raise ValueError("curriculum_based requires a core or required course")
        self.subtags = sorted(self.subtags, key=lambda item: item.value)
        self.courses = sorted(self.courses, key=lambda item: (item.course_name, item.evidence_id))
        return self


class _TaxonomyFieldBase(StrictModel):
    schema_version: Literal["program_taxonomy_field.v1"]
    applicable_academic_year: AcademicYear
    coverage_status: Literal[CoverageStatus.CONFIRMED, CoverageStatus.MANUAL_REVIEW]
    reviewed_source_ids: ReviewedSourceIds
    review_note: ReviewNote | None = None
    reason: CoverageReason | None = None


class PrimaryDirectionFieldV1(_TaxonomyFieldBase):
    field_key: Literal["taxonomy.primary_direction"]
    value: PrimaryDirectionValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "PrimaryDirectionFieldV1":
        _validate_coverage(**_coverage_args(self))
        return self


class SecondaryDirectionsFieldV1(_TaxonomyFieldBase):
    field_key: Literal["taxonomy.secondary_directions"]
    value: SecondaryDirectionsValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "SecondaryDirectionsFieldV1":
        _validate_coverage(**_coverage_args(self))
        return self


class LowAltitudeBasisFieldV1(_TaxonomyFieldBase):
    field_key: Literal["taxonomy.low_altitude_basis"]
    value: LowAltitudeBasisValue | None

    @model_validator(mode="after")
    def validate_contract(self) -> "LowAltitudeBasisFieldV1":
        _validate_coverage(**_coverage_args(self))
        if self.value:
            course_ids = {course.evidence_id for course in self.value.courses}
            if not course_ids.issubset(self.reviewed_source_ids):
                raise ValueError("course evidence must belong to reviewed_source_ids")
        return self


ProgramTaxonomyFieldV1: TypeAlias = Annotated[
    PrimaryDirectionFieldV1 | SecondaryDirectionsFieldV1 | LowAltitudeBasisFieldV1,
    Field(discriminator="field_key"),
]


ProgramFieldPayload: TypeAlias = (
    ProgramCatalogFieldV1 | ProgramRequirementFieldV2 | ProgramTaxonomyFieldV1
)

_PAYLOAD_ADAPTERS = {
    "program_catalog_field.v1": TypeAdapter(ProgramCatalogFieldV1),
    "program_requirement_field.v2": TypeAdapter(ProgramRequirementFieldV2),
    "program_taxonomy_field.v1": TypeAdapter(ProgramTaxonomyFieldV1),
}


def parse_new_program_field_payload(schema_version: str, value: object) -> ProgramFieldPayload:
    adapter = _PAYLOAD_ADAPTERS.get(schema_version)
    if adapter is None:
        raise ValueError(f"unsupported program field schema: {schema_version}")
    return adapter.validate_python(value)


def payload_evidence_ids(payload: ProgramFieldPayload) -> set[str]:
    ids = set(payload.reviewed_source_ids)
    if isinstance(payload, ProgramRequirementFieldV2):
        for requirement in payload.requirements:
            ids.update(requirement.evidence_fixture_ids)
    elif isinstance(payload, LowAltitudeBasisFieldV1) and payload.value is not None:
        ids.update(course.evidence_id for course in payload.value.courses)
    return ids


def payload_display_text(payload: ProgramFieldPayload) -> str | None:
    if isinstance(payload, ProgramRequirementFieldV2):
        if payload.coverage_status == CoverageStatus.CONFIRMED:
            return "；".join(item.display_text for item in payload.requirements)
        return payload.review_note or (payload.reason.detail if payload.reason else None)
    if payload.coverage_status != CoverageStatus.CONFIRMED:
        return payload.review_note or (payload.reason.detail if payload.reason else None)
    if isinstance(payload, LowAltitudeBasisFieldV1) and payload.value is not None:
        return payload.value.rationale_zh
    return None
