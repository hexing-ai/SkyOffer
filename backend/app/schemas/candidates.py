from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, TypeAdapter, field_validator, model_validator

from backend.app.db.models import EvidenceSupportScope, VersionStatus
from backend.app.schemas.evidence import (
    ActorRef,
    Identifier,
    Sha256Hex,
    normalize_aware_utc,
)
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.field_registry import validate_registry_field
from backend.app.schemas.program_fields import (
    CoverageStatus,
    ProgramCatalogFieldV1,
    ProgramFieldPayload,
    ProgramRequirementFieldV2,
    ProgramTaxonomyFieldV1,
    parse_new_program_field_payload,
    payload_display_text,
    payload_evidence_ids,
)
from backend.app.schemas.requirement_rules import RequirementFixture


class ProgramRequirementFieldV1(StrictModel):
    schema_version: Literal["program_requirement_field.v1"]
    applicable_academic_year: Annotated[str, Field(pattern=r"^20\d{2}-\d{2}$")]
    coverage: Literal["score_threshold_only"]
    requirement: RequirementFixture

    @model_validator(mode="after")
    def validate_pilot_requirement(self) -> "ProgramRequirementFieldV1":
        start_year = int(self.applicable_academic_year[:4])
        expected_suffix = f"{(start_year + 1) % 100:02d}"
        if self.applicable_academic_year[-2:] != expected_suffix:
            raise ValueError("applicable_academic_year must describe consecutive years")
        if self.requirement.requirement_type != "language":
            raise ValueError("pilot field only accepts a language requirement")
        if self.requirement.rule.operator not in {"language_minimum", "manual_review"}:
            raise ValueError("pilot field only accepts language_minimum or manual_review")
        evidence_ids = self.requirement.evidence_fixture_ids
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_fixture_ids cannot contain duplicates")
        self.requirement = self.requirement.model_copy(
            update={"evidence_fixture_ids": sorted(evidence_ids)}
        )
        return self


class CandidateEvidenceLinkCreate(StrictModel):
    evidence_id: Identifier
    support_scope: EvidenceSupportScope
    citation_order: Annotated[int, Field(ge=1, le=100)]


ProgramFieldPayloadAny: TypeAlias = ProgramRequirementFieldV1 | ProgramFieldPayload


def parse_program_field_payload(
    schema_version: str, value: object
) -> ProgramFieldPayloadAny:
    if schema_version == "program_requirement_field.v1":
        return ProgramRequirementFieldV1.model_validate(value)
    return parse_new_program_field_payload(schema_version, value)


def _validate_field_contract(field: object) -> None:
    payload = getattr(field, "value_payload")
    field_key = getattr(field, "field_key")
    schema_version = getattr(field, "value_schema_version")
    is_critical = getattr(field, "is_critical")
    links = getattr(field, "evidence_links")
    display_text = getattr(field, "display_text")
    if payload.schema_version != schema_version:
        raise ValueError("value_schema_version must match payload schema_version")
    payload_field_key = getattr(payload, "field_key", "requirements.language.ielts")
    if payload_field_key != field_key:
        raise ValueError("field_key must match payload field_key")
    coverage_status = getattr(payload, "coverage_status", None)
    validate_registry_field(
        field_key=field_key,
        schema_version=schema_version,
        is_critical=is_critical,
        coverage_status=coverage_status,
    )
    evidence_ids = [link.evidence_id for link in links]
    citation_orders = [link.citation_order for link in links]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence_links cannot contain duplicate evidence IDs")
    if len(citation_orders) != len(set(citation_orders)):
        raise ValueError("evidence_links cannot contain duplicate citation_order values")
    expected_evidence = (
        set(payload.requirement.evidence_fixture_ids)
        if isinstance(payload, ProgramRequirementFieldV1)
        else payload_evidence_ids(payload)
    )
    if set(evidence_ids) != expected_evidence:
        raise ValueError("payload evidence IDs must match explicit evidence_links")
    expected_display = (
        payload.requirement.display_text
        if isinstance(payload, ProgramRequirementFieldV1)
        else payload_display_text(payload)
    )
    if expected_display is not None and display_text != expected_display:
        raise ValueError("field display_text must match the payload display contract")
    if coverage_status == CoverageStatus.CONFIRMED and not any(
        link.support_scope == EvidenceSupportScope.DIRECT for link in links
    ):
        raise ValueError("confirmed fields require direct evidence")
    if coverage_status == CoverageStatus.NOT_FOUND_IN_REVIEWED_SOURCES:
        if any(link.support_scope != EvidenceSupportScope.COVERAGE for link in links):
            raise ValueError("not-found fields require coverage-only evidence links")


class _CandidateFieldCreateBase(StrictModel):
    display_text: Annotated[str, Field(min_length=1, max_length=500)]
    is_critical: bool
    evidence_links: Annotated[
        list[CandidateEvidenceLinkCreate], Field(min_length=1, max_length=50)
    ]

    @model_validator(mode="after")
    def validate_field_links(self) -> "_CandidateFieldCreateBase":
        _validate_field_contract(self)
        self.evidence_links = sorted(
            self.evidence_links, key=lambda link: link.citation_order
        )
        return self


class CandidatePilotFieldCreate(_CandidateFieldCreateBase):
    field_key: Literal["requirements.language.ielts"]
    value_schema_version: Literal["program_requirement_field.v1"]
    value_payload: ProgramRequirementFieldV1
    is_critical: Literal[True]


class CandidateCatalogFieldCreate(_CandidateFieldCreateBase):
    field_key: str
    value_schema_version: Literal["program_catalog_field.v1"]
    value_payload: ProgramCatalogFieldV1


class CandidateRequirementFieldCreate(_CandidateFieldCreateBase):
    field_key: str
    value_schema_version: Literal["program_requirement_field.v2"]
    value_payload: ProgramRequirementFieldV2


class CandidateTaxonomyFieldCreate(_CandidateFieldCreateBase):
    field_key: str
    value_schema_version: Literal["program_taxonomy_field.v1"]
    value_payload: ProgramTaxonomyFieldV1


CandidateFieldCreate: TypeAlias = Annotated[
    CandidatePilotFieldCreate
    | CandidateCatalogFieldCreate
    | CandidateRequirementFieldCreate
    | CandidateTaxonomyFieldCreate,
    Field(discriminator="value_schema_version"),
]

_CANDIDATE_FIELD_CREATE_ADAPTER = TypeAdapter(CandidateFieldCreate)


def parse_candidate_field_create(value: object) -> CandidateFieldCreate:
    return _CANDIDATE_FIELD_CREATE_ADAPTER.validate_python(value)


class CandidateCreate(StrictModel):
    base_version_id: Identifier | None = None
    fields: Annotated[list[CandidateFieldCreate], Field(max_length=100)]
    created_by: ActorRef
    creation_note: Annotated[str, Field(min_length=1, max_length=1000)]
    request_id: Identifier

    @model_validator(mode="after")
    def validate_unique_fields(self) -> "CandidateCreate":
        field_keys = [field.field_key for field in self.fields]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("candidate fields must use unique field_key values")
        self.fields = sorted(self.fields, key=lambda field: field.field_key)
        return self


class RollbackCandidateCreate(StrictModel):
    expected_current_version_id: Identifier
    created_by: ActorRef
    creation_note: Annotated[str, Field(min_length=1, max_length=1000)]
    request_id: Identifier


class FieldDiffSide(StrictModel):
    value_sha256: Sha256Hex
    display_text: str


class FieldDiff(StrictModel):
    field_key: str
    change_type: Literal["added", "changed", "removed", "unchanged"]
    before: FieldDiffSide | None
    after: FieldDiffSide | None
    evidence_added: list[Identifier]
    evidence_removed: list[Identifier]


class _CandidateFieldRecordBase(StrictModel):
    id: Identifier
    display_text: str
    is_critical: bool
    value_sha256: Sha256Hex
    evidence_links: list[CandidateEvidenceLinkCreate]

    @model_validator(mode="after")
    def validate_record(self) -> "_CandidateFieldRecordBase":
        _validate_field_contract(self)
        return self


class CandidatePilotFieldRecord(_CandidateFieldRecordBase):
    field_key: Literal["requirements.language.ielts"]
    value_schema_version: Literal["program_requirement_field.v1"]
    value_payload: ProgramRequirementFieldV1
    is_critical: Literal[True]


class CandidateCatalogFieldRecord(_CandidateFieldRecordBase):
    field_key: str
    value_schema_version: Literal["program_catalog_field.v1"]
    value_payload: ProgramCatalogFieldV1


class CandidateRequirementFieldRecord(_CandidateFieldRecordBase):
    field_key: str
    value_schema_version: Literal["program_requirement_field.v2"]
    value_payload: ProgramRequirementFieldV2


class CandidateTaxonomyFieldRecord(_CandidateFieldRecordBase):
    field_key: str
    value_schema_version: Literal["program_taxonomy_field.v1"]
    value_payload: ProgramTaxonomyFieldV1


CandidateFieldRecord: TypeAlias = Annotated[
    CandidatePilotFieldRecord
    | CandidateCatalogFieldRecord
    | CandidateRequirementFieldRecord
    | CandidateTaxonomyFieldRecord,
    Field(discriminator="value_schema_version"),
]

_CANDIDATE_FIELD_RECORD_ADAPTER = TypeAdapter(CandidateFieldRecord)


def parse_candidate_field_record(value: object) -> CandidateFieldRecord:
    return _CANDIDATE_FIELD_RECORD_ADAPTER.validate_python(value)


class CandidateRecord(StrictModel):
    id: Identifier
    program_id: Identifier
    version_no: int
    base_version_id: Identifier | None
    rollback_of_version_id: Identifier | None
    status: VersionStatus
    content_schema_version: Literal["program_version_content.v1"]
    content_sha256: Sha256Hex
    created_by: ActorRef
    created_at: datetime
    fields: list[CandidateFieldRecord]
    diff: list[FieldDiff]

    @field_validator("created_at", mode="after")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)
