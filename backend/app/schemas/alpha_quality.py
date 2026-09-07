from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.evidence import Identifier, Sha256Hex, normalize_aware_utc
from backend.app.schemas.profile_analysis import StrictModel


HardGateName = Literal[
    "scope_compliance_rate",
    "field_inventory_completion_rate",
    "critical_citation_coverage_rate",
    "fresh_evidence_at_publish_rate",
    "four_eye_review_rate",
    "published_only_isolation_rate",
    "low_altitude_evidence_coverage_rate",
    "pack_to_database_semantic_match_rate",
]


class AlphaQualityMetric(StrictModel):
    numerator: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=0)]
    rate: Annotated[Decimal, Field(ge=0, le=1)]
    passed: bool

    @model_validator(mode="after")
    def validate_ratio(self) -> "AlphaQualityMetric":
        expected = (
            Decimal(self.numerator) / Decimal(self.denominator)
            if self.denominator
            else Decimal(0)
        )
        if self.numerator > self.denominator:
            raise ValueError("quality numerator cannot exceed denominator")
        if self.rate != expected or self.passed != (expected == Decimal(1)):
            raise ValueError("quality rate and pass state must be derived from counts")
        return self


class AlphaHardGateMetrics(StrictModel):
    scope_compliance_rate: AlphaQualityMetric
    field_inventory_completion_rate: AlphaQualityMetric
    critical_citation_coverage_rate: AlphaQualityMetric
    fresh_evidence_at_publish_rate: AlphaQualityMetric
    four_eye_review_rate: AlphaQualityMetric
    published_only_isolation_rate: AlphaQualityMetric
    low_altitude_evidence_coverage_rate: AlphaQualityMetric
    pack_to_database_semantic_match_rate: AlphaQualityMetric


class AlphaQualityDistributions(StrictModel):
    region_counts: dict[str, Annotated[int, Field(ge=0)]]
    institution_counts: dict[str, Annotated[int, Field(ge=0)]]
    primary_direction_counts: dict[str, Annotated[int, Field(ge=0)]]
    secondary_direction_counts: dict[str, Annotated[int, Field(ge=0)]]
    coverage_status_counts: dict[str, Annotated[int, Field(ge=0)]]
    review_duration_seconds_by_program: dict[
        Identifier, Annotated[int, Field(ge=0)]
    ]


class AlphaProgramQualityResult(StrictModel):
    pack_ref: Identifier
    program_ref: Identifier
    published_version_id: Identifier | None
    scope_compliant: bool
    expected_field_count: Annotated[int, Field(ge=1)]
    present_field_count: Annotated[int, Field(ge=0)]
    expected_critical_field_count: Annotated[int, Field(ge=1)]
    qualified_critical_field_count: Annotated[int, Field(ge=0)]
    fresh_at_publish: bool
    four_eye_reviewed: bool
    published_only_isolated: bool
    low_altitude_evidence_complete: bool
    pack_database_semantic_match: bool
    issues: list[str]

    @model_validator(mode="after")
    def normalize_result(self) -> "AlphaProgramQualityResult":
        if self.present_field_count > self.expected_field_count:
            raise ValueError("present field count cannot exceed expected field count")
        if self.qualified_critical_field_count > self.expected_critical_field_count:
            raise ValueError(
                "qualified critical count cannot exceed expected critical count"
            )
        if len(self.issues) != len(set(self.issues)):
            raise ValueError("program quality issues cannot contain duplicates")
        self.issues = sorted(self.issues)
        return self


class AlphaQualityReport(StrictModel):
    schema_version: Literal["alpha_quality_report.v1"]
    dataset_id: Identifier
    generated_at: datetime
    generated_commit: Annotated[str, Field(min_length=1, max_length=80)]
    alembic_revision: Annotated[str, Field(min_length=1, max_length=80)]
    registry_schema_version: Literal["program_field_registry.v1"]
    registry_version: Literal["1.0.0"]
    registry_sha256: Sha256Hex
    scope_schema_version: Literal["alpha_scope_snapshot.v1"]
    scope_snapshot_id: Identifier | None
    scope_sha256: Sha256Hex
    manifest_schema_version: Literal["alpha_program_manifest.v1"]
    manifest_sha256: Sha256Hex
    pack_canonical_sha256_by_ref: dict[Identifier, Sha256Hex]
    input_fingerprint_sha256: Sha256Hex
    published_program_count: Annotated[int, Field(ge=0)]
    hard_gates: AlphaHardGateMetrics
    blocking_gates: list[str]
    ready: bool
    distributions: AlphaQualityDistributions
    programs: list[AlphaProgramQualityResult]
    structural_issues: list[str]

    @field_validator("generated_at", mode="after")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)

    @model_validator(mode="after")
    def validate_report(self) -> "AlphaQualityReport":
        if len(self.programs) != len({item.pack_ref for item in self.programs}):
            raise ValueError("quality report pack refs must be unique")
        metric_failures = sorted(
            name
            for name, metric in self.hard_gates.model_dump(mode="python").items()
            if not metric["passed"]
        )
        expected_blocking = sorted(
            [*metric_failures, *("structural_contract" for _ in self.structural_issues[:1])]
        )
        if sorted(self.blocking_gates) != expected_blocking:
            raise ValueError("blocking gates must be derived from metrics and structure")
        if self.ready != (not expected_blocking):
            raise ValueError("ready must be derived from blocking gates")
        if len(self.structural_issues) != len(set(self.structural_issues)):
            raise ValueError("structural issues cannot contain duplicates")
        self.blocking_gates = sorted(self.blocking_gates)
        self.structural_issues = sorted(self.structural_issues)
        self.programs = sorted(self.programs, key=lambda item: item.pack_ref)
        self.pack_canonical_sha256_by_ref = dict(
            sorted(self.pack_canonical_sha256_by_ref.items())
        )
        return self
