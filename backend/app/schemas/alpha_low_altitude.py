from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.app.schemas.evidence import Identifier
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.program_fields import (
    LowAltitudeInclusionBasis,
    LowAltitudeSubtag,
    ProgramDirection,
)


class AlphaLowAltitudeIssueCode(StrEnum):
    BASIS_MISSING = "LOW_ALTITUDE_BASIS_MISSING"
    BASIS_FORBIDDEN = "LOW_ALTITUDE_BASIS_FORBIDDEN"
    BASIS_NOT_CRITICAL = "LOW_ALTITUDE_BASIS_NOT_CRITICAL"
    BASIS_NOT_CONFIRMED = "LOW_ALTITUDE_BASIS_NOT_CONFIRMED"
    BASIS_VALUE_MISSING = "LOW_ALTITUDE_BASIS_VALUE_MISSING"
    RATIONALE_NOT_CHINESE = "LOW_ALTITUDE_RATIONALE_NOT_CHINESE"
    COURSE_NAME_DUPLICATE = "LOW_ALTITUDE_COURSE_NAME_DUPLICATE"
    SUBTAG_WITHOUT_COURSE = "LOW_ALTITUDE_SUBTAG_WITHOUT_COURSE"
    COURSE_EVIDENCE_MISSING = "LOW_ALTITUDE_COURSE_EVIDENCE_MISSING"
    COURSE_EVIDENCE_PROGRAM_MISMATCH = (
        "LOW_ALTITUDE_COURSE_EVIDENCE_PROGRAM_MISMATCH"
    )
    COURSE_EVIDENCE_NOT_V2 = "LOW_ALTITUDE_COURSE_EVIDENCE_NOT_V2"
    COURSE_EVIDENCE_NOT_CURRICULUM = (
        "LOW_ALTITUDE_COURSE_EVIDENCE_NOT_CURRICULUM"
    )
    COURSE_EVIDENCE_NOT_DIRECT = "LOW_ALTITUDE_COURSE_EVIDENCE_NOT_DIRECT"
    COURSE_NAME_NOT_IN_EXCERPT = "LOW_ALTITUDE_COURSE_NAME_NOT_IN_EXCERPT"
    COURSE_TYPE_NOT_IN_EXCERPT = "LOW_ALTITUDE_COURSE_TYPE_NOT_IN_EXCERPT"
    EXPLICIT_FOCUS_EVIDENCE_MISSING = (
        "LOW_ALTITUDE_EXPLICIT_FOCUS_EVIDENCE_MISSING"
    )


class AlphaLowAltitudeIssue(StrictModel):
    code: AlphaLowAltitudeIssueCode
    message: Annotated[str, Field(min_length=1, max_length=500)]
    course_name: Annotated[str | None, Field(default=None, max_length=300)]
    evidence_id: Identifier | None = None


class AlphaLowAltitudeValidationReport(StrictModel):
    schema_version: Literal["alpha_low_altitude_validation_report.v1"]
    program_ref: Identifier
    applies: bool
    primary_direction: ProgramDirection | None
    secondary_directions: Annotated[list[ProgramDirection], Field(max_length=4)]
    inclusion_basis: LowAltitudeInclusionBasis | None
    declared_subtags: Annotated[list[LowAltitudeSubtag], Field(max_length=7)]
    course_count: Annotated[int, Field(ge=0, le=50)]
    verified_course_evidence_ids: Annotated[list[Identifier], Field(max_length=50)]
    valid: Literal[True]

    @model_validator(mode="after")
    def normalize_report(self) -> "AlphaLowAltitudeValidationReport":
        self.secondary_directions = sorted(
            self.secondary_directions, key=lambda item: item.value
        )
        self.declared_subtags = sorted(
            self.declared_subtags, key=lambda item: item.value
        )
        self.verified_course_evidence_ids = sorted(
            self.verified_course_evidence_ids
        )
        if len(self.secondary_directions) != len(set(self.secondary_directions)):
            raise ValueError("secondary_directions cannot contain duplicates")
        if len(self.declared_subtags) != len(set(self.declared_subtags)):
            raise ValueError("declared_subtags cannot contain duplicates")
        if len(self.verified_course_evidence_ids) != len(
            set(self.verified_course_evidence_ids)
        ):
            raise ValueError("verified course Evidence IDs cannot contain duplicates")
        if not self.applies and (
            self.inclusion_basis is not None
            or self.declared_subtags
            or self.course_count
            or self.verified_course_evidence_ids
        ):
            raise ValueError("non-low-altitude reports cannot contain basis results")
        return self
