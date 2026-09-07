from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.evidence import Sha256Hex, normalize_aware_utc, normalize_official_url
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.requirement_evaluation import RequirementStatus
from backend.app.schemas.requirement_rules import RequirementFixture


class HistoricalReferenceAvailability(StrEnum):
    EVALUABLE = "evaluable"
    LIMITED = "limited"


class HistoricalReferenceSource(StrictModel):
    source_id: str
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    page_title: Annotated[str, Field(min_length=1, max_length=500)]
    excerpt: Annotated[str, Field(min_length=1, max_length=4000)]
    source_version: Annotated[str, Field(min_length=1, max_length=200)]
    verified_at: datetime
    snapshot_sha256: Sha256Hex

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_official_url(value)

    @field_validator("verified_at", mode="after")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


class HistoricalReferenceField(StrictModel):
    field_key: Literal[
        "requirements.degree",
        "requirements.academic",
        "requirements.subject",
        "requirements.prerequisite_courses",
        "requirements.language",
    ]
    display_text: Annotated[str, Field(min_length=1, max_length=1000)]
    requirement: RequirementFixture
    source_ids: Annotated[list[str], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def field_matches_requirement(self) -> "HistoricalReferenceField":
        expected_type = {
            "requirements.degree": "degree",
            "requirements.academic": "academic",
            "requirements.subject": "subject",
            "requirements.prerequisite_courses": "course",
            "requirements.language": "language",
        }[self.field_key]
        if self.requirement.requirement_type != expected_type:
            raise ValueError("historical field and requirement type differ")
        if set(self.requirement.evidence_fixture_ids) != set(self.source_ids):
            raise ValueError("historical field source IDs must match requirement evidence")
        return self


class HistoricalProgramReference(StrictModel):
    program_ref: str
    academic_year: Literal["2026-27"]
    availability: HistoricalReferenceAvailability
    sources: Annotated[list[HistoricalReferenceSource], Field(min_length=1, max_length=20)]
    fields: Annotated[list[HistoricalReferenceField], Field(max_length=20)]
    limitation_note: Annotated[str | None, Field(default=None, min_length=1, max_length=1000)]

    @model_validator(mode="after")
    def validate_inventory(self) -> "HistoricalProgramReference":
        source_ids = [item.source_id for item in self.sources]
        field_keys = [item.field_key for item in self.fields]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("historical source IDs must be unique")
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("historical field keys must be unique")
        if any(not set(item.source_ids).issubset(source_ids) for item in self.fields):
            raise ValueError("historical field references an unknown source")
        if self.availability == HistoricalReferenceAvailability.EVALUABLE and not self.fields:
            raise ValueError("evaluable historical reference requires fields")
        if self.availability == HistoricalReferenceAvailability.LIMITED and not self.limitation_note:
            raise ValueError("limited historical reference requires a limitation note")
        return self


class HistoricalReferenceDataset(StrictModel):
    schema_version: Literal["historical_reference_dataset.v1"]
    dataset_id: str
    academic_year: Literal["2026-27"]
    generated_at: datetime
    public_publishable: Literal[False]
    programs: Annotated[list[HistoricalProgramReference], Field(min_length=1, max_length=30)]

    @field_validator("generated_at", mode="after")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)

    @model_validator(mode="after")
    def unique_programs(self) -> "HistoricalReferenceDataset":
        refs = [item.program_ref for item in self.programs]
        if len(refs) != len(set(refs)):
            raise ValueError("historical Program refs must be unique")
        return self


class HistoricalCitation(StrictModel):
    source_id: str
    field_key: str
    academic_year: Literal["2026-27"]
    url: str
    page_title: str
    excerpt: str
    source_version: str
    verified_at: datetime
    snapshot_sha256: Sha256Hex


class HistoricalFieldJudgment(StrictModel):
    field_key: str
    status: RequirementStatus
    display_text: str
    reason_code: str
    citations: Annotated[list[HistoricalCitation], Field(min_length=1, max_length=20)]


class HistoricalReferenceSummary(StrictModel):
    met: Annotated[int, Field(ge=0)]
    unmet: Annotated[int, Field(ge=0)]
    missing_information: Annotated[int, Field(ge=0)]
    manual_review: Annotated[int, Field(ge=0)]


class HistoricalReferenceResult(StrictModel):
    academic_year: Literal["2026-27"]
    availability: HistoricalReferenceAvailability
    reference_status: Literal["met", "partial", "unmet", "unavailable"]
    reference_label: Literal["满足", "部分满足", "未满足", "资料不足"]
    summary: HistoricalReferenceSummary
    field_judgments: list[HistoricalFieldJudgment]
    limitation_note: str | None
    disclaimer: Literal[
        "以下仅按 2026/27 官方门槛计算历史参考，不代表 2027/28 要求，也不参与 2027 推荐分层。"
    ]
