from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, TypeAdapter, field_validator, model_validator

from backend.app.db.models import (
    EvidenceSupportScope,
    ProgramRegion,
    SourceType,
)
from backend.app.schemas.candidates import ProgramRequirementFieldV1
from backend.app.schemas.field_registry import validate_registry_field
from backend.app.schemas.evidence import (
    ActorRef,
    EvidenceFreshness,
    Identifier,
    Sha256Hex,
    EvidenceCaptureMethod,
    EvidenceHashScope,
    ReviewedSourceRole,
    normalize_aware_utc,
)
from backend.app.schemas.program_fields import (
    CoverageStatus,
    ProgramCatalogFieldV1,
    ProgramRequirementFieldV2,
    ProgramTaxonomyFieldV1,
    payload_display_text,
    payload_evidence_ids,
)
from backend.app.schemas.profile_analysis import StrictModel


class PublishedEvidenceCitation(StrictModel):
    evidence_id: Identifier
    source_type: SourceType
    url: str
    official_domain: str
    page_title: str
    excerpt: str
    snapshot_sha256: Sha256Hex
    source_version: str
    verified_at: datetime
    verified_by: ActorRef
    review_due_at: datetime
    expires_at: datetime
    freshness: EvidenceFreshness
    support_scope: EvidenceSupportScope
    citation_order: Annotated[int, Field(ge=1)]

    @field_validator(
        "verified_at", "review_due_at", "expires_at", mode="after"
    )
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


class PublishedEvidenceCitationV2(PublishedEvidenceCitation):
    schema_version: Literal["source_evidence.v2"]
    capture_method: EvidenceCaptureMethod
    hash_scope: EvidenceHashScope
    reviewed_source_role: ReviewedSourceRole


PublishedEvidenceCitationAny: TypeAlias = (
    PublishedEvidenceCitationV2 | PublishedEvidenceCitation
)


class _PublishedProgramFieldBase(StrictModel):
    display_text: str
    is_critical: bool
    value_sha256: Sha256Hex
    evidence: Annotated[list[PublishedEvidenceCitationAny], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_field_contract(self) -> "_PublishedProgramFieldBase":
        payload = getattr(self, "value_payload")
        schema_version = getattr(self, "value_schema_version")
        field_key = getattr(self, "field_key")
        if payload.schema_version != schema_version:
            raise ValueError("value_schema_version must match payload schema_version")
        payload_field_key = getattr(payload, "field_key", "requirements.language.ielts")
        if field_key != payload_field_key:
            raise ValueError("field_key must match payload field_key")
        coverage_status = getattr(payload, "coverage_status", None)
        validate_registry_field(
            field_key=field_key,
            schema_version=schema_version,
            is_critical=self.is_critical,
            coverage_status=coverage_status,
        )
        expected_ids = (
            set(payload.requirement.evidence_fixture_ids)
            if isinstance(payload, ProgramRequirementFieldV1)
            else payload_evidence_ids(payload)
        )
        citation_ids = [citation.evidence_id for citation in self.evidence]
        if len(citation_ids) != len(set(citation_ids)) or set(citation_ids) != expected_ids:
            raise ValueError("published evidence must match payload evidence IDs")
        expected_display = (
            payload.requirement.display_text
            if isinstance(payload, ProgramRequirementFieldV1)
            else payload_display_text(payload)
        )
        if expected_display is not None and self.display_text != expected_display:
            raise ValueError("published display_text must match payload display contract")
        if coverage_status == CoverageStatus.CONFIRMED and not any(
            citation.support_scope == EvidenceSupportScope.DIRECT
            for citation in self.evidence
        ):
            raise ValueError("confirmed published fields require direct evidence")
        if coverage_status == CoverageStatus.NOT_FOUND_IN_REVIEWED_SOURCES and any(
            citation.support_scope != EvidenceSupportScope.COVERAGE
            for citation in self.evidence
        ):
            raise ValueError("not-found published fields require coverage-only evidence")
        return self


class PublishedPilotProgramField(_PublishedProgramFieldBase):
    field_key: Literal["requirements.language.ielts"]
    value_schema_version: Literal["program_requirement_field.v1"]
    value_payload: ProgramRequirementFieldV1
    is_critical: Literal[True]


class PublishedCatalogProgramField(_PublishedProgramFieldBase):
    field_key: str
    value_schema_version: Literal["program_catalog_field.v1"]
    value_payload: ProgramCatalogFieldV1


class PublishedRequirementProgramField(_PublishedProgramFieldBase):
    field_key: str
    value_schema_version: Literal["program_requirement_field.v2"]
    value_payload: ProgramRequirementFieldV2


class PublishedTaxonomyProgramField(_PublishedProgramFieldBase):
    field_key: str
    value_schema_version: Literal["program_taxonomy_field.v1"]
    value_payload: ProgramTaxonomyFieldV1


PublishedProgramField: TypeAlias = Annotated[
    PublishedPilotProgramField
    | PublishedCatalogProgramField
    | PublishedRequirementProgramField
    | PublishedTaxonomyProgramField,
    Field(discriminator="value_schema_version"),
]

_PUBLISHED_PROGRAM_FIELD_ADAPTER = TypeAdapter(PublishedProgramField)


def parse_published_program_field(value: object) -> PublishedProgramField:
    return _PUBLISHED_PROGRAM_FIELD_ADAPTER.validate_python(value)


class PublishedProgramRecord(StrictModel):
    program_id: Identifier
    official_name: str
    institution_name: str
    region: ProgramRegion
    official_program_url: str
    version_id: Identifier
    version_no: Annotated[int, Field(gt=0)]
    content_schema_version: Literal["program_version_content.v1"]
    content_sha256: Sha256Hex
    published_at: datetime
    fields: Annotated[list[PublishedProgramField], Field(min_length=1)]

    @field_validator("published_at", mode="after")
    @classmethod
    def normalize_published_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)
