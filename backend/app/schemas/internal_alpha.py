from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.db.models import ProgramRegion
from backend.app.schemas.evidence import Identifier, Sha256Hex, normalize_aware_utc
from backend.app.schemas.profile_analysis import StrictModel


class InternalAlphaProgram(StrictModel):
    pack_ref: Identifier
    pack_path: Annotated[str, Field(min_length=1, max_length=240)]
    pack_file_sha256: Sha256Hex
    pack_canonical_sha256: Sha256Hex
    candidate_semantic_sha256: Sha256Hex
    program_ref: Identifier
    candidate_version_id: Identifier
    institution_ref: Identifier
    region: ProgramRegion

    @field_validator("pack_path")
    @classmethod
    def validate_pack_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or path.parent != PurePosixPath("programs")
            or path.suffix != ".json"
            or ".." in path.parts
        ):
            raise ValueError("pack_path must be one JSON file inside programs/")
        return value


class InternalAlphaManifestV1(StrictModel):
    schema_version: Literal["internal_alpha_manifest.v1"]
    dataset_id: Identifier
    target_academic_year: Literal["2027-28"]
    lifecycle_state: Literal["quality_gated"]
    use_boundary: Literal["internal_candidate_only"]
    public_publishable: Literal[False]
    source_scope_snapshot_id: Identifier
    field_registry_schema_version: Literal["program_field_registry.v1"]
    field_registry_version: Literal["1.0.0"]
    governance_policy: Literal[
        "automatic_gates_then_risk_review_then_batch_release"
    ]
    created_at: datetime
    created_by: Literal["actor.data_preparer.codex"]
    approved_by: Literal["actor.domain_reviewer.product_owner"]
    program_count: Annotated[int, Field(ge=1, le=30)]
    programs: Annotated[list[InternalAlphaProgram], Field(min_length=1, max_length=30)]
    manifest_sha256: Sha256Hex

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)

    @model_validator(mode="after")
    def validate_programs(self) -> "InternalAlphaManifestV1":
        if self.program_count != len(self.programs):
            raise ValueError("program_count must equal programs length")
        for attr in (
            "pack_ref",
            "pack_path",
            "program_ref",
            "candidate_version_id",
        ):
            values = [getattr(item, attr) for item in self.programs]
            if len(values) != len(set(values)):
                raise ValueError(f"internal Alpha {attr} values must be unique")
        self.programs = sorted(self.programs, key=lambda item: item.pack_ref)
        return self


class InternalAlphaQualityMetric(StrictModel):
    numerator: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=0)]
    rate: Annotated[Decimal, Field(ge=0, le=1)]
    passed: bool

    @model_validator(mode="after")
    def validate_ratio(self) -> "InternalAlphaQualityMetric":
        expected = (
            Decimal(self.numerator) / Decimal(self.denominator)
            if self.denominator
            else Decimal(0)
        )
        if self.numerator > self.denominator:
            raise ValueError("quality numerator cannot exceed denominator")
        if self.rate != expected or self.passed != (expected == Decimal(1)):
            raise ValueError("quality metric must be derived from its counts")
        return self


class InternalAlphaProgramQualityResult(StrictModel):
    pack_ref: Identifier
    program_ref: Identifier
    candidate_version_id: Identifier
    field_count: Annotated[int, Field(ge=0)]
    evidence_count: Annotated[int, Field(ge=0)]
    high_risk_field_keys: list[str]
    exception_field_keys: list[str]
    passed: bool
    issues: list[str]

    @model_validator(mode="after")
    def normalize_result(self) -> "InternalAlphaProgramQualityResult":
        self.high_risk_field_keys = sorted(set(self.high_risk_field_keys))
        self.exception_field_keys = sorted(set(self.exception_field_keys))
        self.issues = sorted(set(self.issues))
        if self.passed != (not self.issues):
            raise ValueError("program pass state must be derived from issues")
        return self


class InternalAlphaQualityGates(StrictModel):
    manifest_integrity: InternalAlphaQualityMetric
    pack_contract: InternalAlphaQualityMetric
    field_inventory: InternalAlphaQualityMetric
    official_fresh_evidence: InternalAlphaQualityMetric
    candidate_database_match: InternalAlphaQualityMetric
    candidate_only_isolation: InternalAlphaQualityMetric
    risk_and_exception_disclosure: InternalAlphaQualityMetric


class InternalAlphaQualityReport(StrictModel):
    schema_version: Literal["internal_alpha_quality_report.v1"]
    dataset_id: Identifier
    generated_at: datetime
    generated_commit: Annotated[str, Field(min_length=1, max_length=80)]
    manifest_sha256: Sha256Hex
    input_fingerprint_sha256: Sha256Hex
    program_count: Annotated[int, Field(ge=1, le=30)]
    gates: InternalAlphaQualityGates
    blocking_gates: list[str]
    ready_for_internal_mvp: bool
    programs: list[InternalAlphaProgramQualityResult]
    structural_issues: list[str]

    @field_validator("generated_at", mode="after")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)

    @model_validator(mode="after")
    def validate_report(self) -> "InternalAlphaQualityReport":
        metric_failures = sorted(
            key
            for key, value in self.gates.model_dump(mode="python").items()
            if not value["passed"]
        )
        expected = sorted(
            [*metric_failures, *("structural_contract" for _ in self.structural_issues[:1])]
        )
        if sorted(self.blocking_gates) != expected:
            raise ValueError("blocking gates must be derived from metrics and structure")
        if self.ready_for_internal_mvp != (not expected):
            raise ValueError("internal readiness must be derived from blocking gates")
        self.blocking_gates = expected
        self.structural_issues = sorted(set(self.structural_issues))
        self.programs = sorted(self.programs, key=lambda item: item.pack_ref)
        return self
