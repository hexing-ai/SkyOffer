from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.db.models import EvidenceSupportScope, ProgramRegion, VersionStatus
from backend.app.schemas.alpha_quality import HardGateName
from backend.app.schemas.candidates import FieldDiff
from backend.app.schemas.evidence import (
    ActorRef,
    EvidenceFreshness,
    Identifier,
    Sha256Hex,
    normalize_aware_utc,
)
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.program_fields import ProgramDirection


ReviewGateStatus = Literal["pass", "block", "pending"]


class AlphaReviewGate(StrictModel):
    name: HardGateName
    label: Annotated[str, Field(min_length=1, max_length=80)]
    status: ReviewGateStatus
    detail: Annotated[str, Field(min_length=1, max_length=500)]
    blocking: bool

    @model_validator(mode="after")
    def derive_blocking(self) -> "AlphaReviewGate":
        if self.blocking != (self.status == "block"):
            raise ValueError("gate blocking must be derived from status")
        return self


class AlphaReviewEvidence(StrictModel):
    evidence_id: Identifier
    support_scope: EvidenceSupportScope
    citation_order: Annotated[int, Field(ge=1, le=50)]
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    page_title: Annotated[str, Field(min_length=1, max_length=500)]
    excerpt: Annotated[str, Field(min_length=1, max_length=4000)]
    snapshot_sha256: Sha256Hex
    hash_scope: Literal["normalized_excerpt", "full_document_bytes"]
    reviewed_source_role: Literal[
        "program",
        "admissions_policy",
        "language_policy",
        "curriculum",
        "scope_notice",
    ]
    verified_by: ActorRef
    verified_at: datetime
    review_due_at: datetime
    expires_at: datetime
    freshness: EvidenceFreshness

    @field_validator("verified_at", "review_due_at", "expires_at", mode="after")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


class AlphaReviewField(StrictModel):
    field_key: Annotated[str, Field(min_length=1, max_length=120)]
    display_label: Annotated[str, Field(min_length=1, max_length=120)]
    display_text: Annotated[str, Field(min_length=1, max_length=1000)]
    coverage_status: Annotated[str, Field(min_length=1, max_length=80)]
    is_critical: bool
    value_sha256: Sha256Hex
    value_payload: dict[str, object]
    diff: FieldDiff
    evidence: Annotated[list[AlphaReviewEvidence], Field(min_length=1, max_length=50)]

    @model_validator(mode="after")
    def normalize_evidence(self) -> "AlphaReviewField":
        if self.diff.field_key != self.field_key:
            raise ValueError("field diff must match field_key")
        orders = [item.citation_order for item in self.evidence]
        if len(orders) != len(set(orders)):
            raise ValueError("field Evidence citation orders must be unique")
        self.evidence = sorted(self.evidence, key=lambda item: item.citation_order)
        return self


class AlphaReviewVersion(StrictModel):
    version_id: Identifier
    version_no: Annotated[int, Field(ge=1)]
    status: VersionStatus
    content_sha256: Sha256Hex
    base_version_id: Identifier | None
    submitted_by: ActorRef | None
    reviewed_by: ActorRef | None
    review_note: Annotated[str | None, Field(default=None, max_length=1000)]
    submitted_at: datetime | None
    reviewed_at: datetime | None
    published_at: datetime | None

    @field_validator("submitted_at", "reviewed_at", "published_at", mode="after")
    @classmethod
    def normalize_optional_timestamp(cls, value: datetime | None) -> datetime | None:
        return normalize_aware_utc(value) if value is not None else None


class AlphaReviewProgramSummary(StrictModel):
    pack_ref: Identifier
    program_ref: Identifier
    official_name: Annotated[str, Field(min_length=1, max_length=300)]
    institution_name: Annotated[str, Field(min_length=1, max_length=300)]
    region: ProgramRegion
    primary_direction: ProgramDirection
    secondary_directions: Annotated[list[ProgramDirection], Field(max_length=3)]
    version_id: Identifier | None
    status: VersionStatus | Literal["missing"]


class AlphaReviewProgramList(StrictModel):
    schema_version: Literal["alpha_review_program_list.v1"]
    dataset_id: Identifier
    manifest_sha256: Sha256Hex
    scope_snapshot_id: Identifier
    total: Annotated[int, Field(ge=0, le=30)]
    offset: Annotated[int, Field(ge=0, le=30)]
    limit: Annotated[int, Field(ge=1, le=30)]
    programs: Annotated[list[AlphaReviewProgramSummary], Field(max_length=30)]

    @model_validator(mode="after")
    def normalize_programs(self) -> "AlphaReviewProgramList":
        if len(self.programs) > self.limit or self.total < len(self.programs):
            raise ValueError("program pagination counts are inconsistent")
        if len(self.programs) != len({item.pack_ref for item in self.programs}):
            raise ValueError("program list pack refs must be unique")
        self.programs = sorted(self.programs, key=lambda item: item.pack_ref)
        return self


class AlphaReviewProgramDetail(StrictModel):
    schema_version: Literal["alpha_review_program_detail.v1"]
    dataset_id: Identifier
    manifest_sha256: Sha256Hex
    scope_snapshot_id: Identifier
    generated_at: datetime
    program: AlphaReviewProgramSummary
    version: AlphaReviewVersion
    current_published_version_id: Identifier | None
    expected_field_count: Annotated[int, Field(ge=1, le=16)]
    critical_field_count: Annotated[int, Field(ge=1, le=16)]
    reviewed_field_count: Literal[0]
    fields: Annotated[list[AlphaReviewField], Field(min_length=1, max_length=16)]
    gates: Annotated[list[AlphaReviewGate], Field(min_length=8, max_length=8)]
    preflight_ready: bool
    can_publish: bool
    can_reject: bool
    reviewer_actor: Literal["actor.domain_reviewer.product_owner"]
    boundary_notice: Literal[
        "人工数据质检 · 无抓取 · 无模型 · 无推荐 · 非正式运营后台"
    ]

    @field_validator("generated_at", mode="after")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)

    @model_validator(mode="after")
    def validate_detail_contract(self) -> "AlphaReviewProgramDetail":
        if len(self.fields) != len({item.field_key for item in self.fields}):
            raise ValueError("review fields must be unique")
        if {item.name for item in self.gates} != {
            "scope_compliance_rate",
            "field_inventory_completion_rate",
            "critical_citation_coverage_rate",
            "fresh_evidence_at_publish_rate",
            "four_eye_review_rate",
            "published_only_isolation_rate",
            "low_altitude_evidence_coverage_rate",
            "pack_to_database_semantic_match_rate",
        }:
            raise ValueError("review detail must expose all eight hard gates")
        expected_ready = (
            self.version.status == VersionStatus.PENDING_REVIEW
            and not any(item.blocking for item in self.gates)
        )
        if self.preflight_ready != expected_ready:
            raise ValueError("preflight_ready must be derived from status and gates")
        if self.can_publish != self.preflight_ready:
            raise ValueError("can_publish must equal preflight readiness")
        if self.can_reject != (self.version.status == VersionStatus.PENDING_REVIEW):
            raise ValueError("can_reject must be derived from version status")
        self.fields = sorted(self.fields, key=lambda item: item.field_key)
        self.gates = sorted(self.gates, key=lambda item: item.name)
        return self
