from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from backend.app.db.models import ProgramRegion
from backend.app.schemas.evidence import (
    EvidenceFreshness,
    Identifier,
    Sha256Hex,
    normalize_aware_utc,
)
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.program_fields import CoverageStatus, ProgramDirection


class ProgramCatalogDataset(StrictModel):
    dataset_id: Identifier
    target_academic_year: Literal["2027-28"]
    program_count: Annotated[int, Field(ge=1, le=30)]
    data_boundary: Literal["internal_candidate_only"]
    public_publishable: Literal[False]
    manifest_sha256: Sha256Hex


class ProgramCoverageSummary(StrictModel):
    confirmed: Annotated[int, Field(ge=0)]
    unresolved: Annotated[int, Field(ge=0)]
    total: Annotated[int, Field(ge=1)]


class ProgramCatalogItem(StrictModel):
    program_ref: Identifier
    official_name: str
    institution_name: str
    region: ProgramRegion
    official_program_url: str
    target_academic_year: Literal["2027-28"]
    degree_type: Literal["taught_masters"]
    primary_direction: ProgramDirection
    secondary_directions: list[ProgramDirection]
    review_status: Literal["domain_reviewed"]
    has_unresolved_fields: bool
    reviewed_at: datetime
    candidate_version_id: Identifier
    pack_ref: Identifier
    pack_schema_version: Literal["alpha_program_pack.v1"]
    pack_canonical_sha256: Sha256Hex
    evidence_count: Annotated[int, Field(ge=1)]
    coverage: ProgramCoverageSummary

    @field_validator("reviewed_at", mode="after")
    @classmethod
    def normalize_reviewed_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


class ProgramFieldCitation(StrictModel):
    evidence_id: Identifier
    support_scope: Literal["direct", "applicability", "definition", "coverage"]
    citation_order: Annotated[int, Field(ge=1)]
    url: str
    page_title: str
    excerpt: str
    source_version: str
    verified_at: datetime
    review_due_at: datetime
    expires_at: datetime
    freshness: EvidenceFreshness

    @field_validator("verified_at", "review_due_at", "expires_at", mode="after")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


class ProgramCatalogField(StrictModel):
    field_key: str
    label: str
    group: Literal["项目概况", "专业方向", "申请门槛"]
    display_text: str
    coverage_status: CoverageStatus
    is_critical: bool
    value_schema_version: str
    citations: Annotated[list[ProgramFieldCitation], Field(min_length=1)]


class ProgramCatalogDetail(ProgramCatalogItem):
    fields: Annotated[list[ProgramCatalogField], Field(min_length=1)]


class ProgramCatalogListResponse(StrictModel):
    schema_version: Literal["program_catalog_list.v1"]
    dataset: ProgramCatalogDataset
    programs: list[ProgramCatalogItem]


class ProgramCatalogDetailResponse(StrictModel):
    schema_version: Literal["program_catalog_detail.v1"]
    dataset: ProgramCatalogDataset
    program: ProgramCatalogDetail
