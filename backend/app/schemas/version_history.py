from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated

from pydantic import Field, field_validator

from backend.app.db.models import ActorRole, AuditEventType, VersionStatus
from backend.app.schemas.candidates import CandidateFieldRecord, FieldDiff
from backend.app.schemas.evidence import ActorRef, Identifier, Sha256Hex, normalize_aware_utc
from backend.app.schemas.profile_analysis import StrictModel


class InternalVersionSummary(StrictModel):
    id: Identifier
    program_id: Identifier
    version_no: Annotated[int, Field(gt=0)]
    base_version_id: Identifier | None
    rollback_of_version_id: Identifier | None
    status: VersionStatus
    content_schema_version: str
    content_sha256: Sha256Hex
    created_by: ActorRef
    submitted_by: ActorRef | None
    reviewed_by: ActorRef | None
    review_note: str | None
    created_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    published_at: datetime | None

    @field_validator(
        "created_at",
        "submitted_at",
        "reviewed_at",
        "published_at",
        mode="after",
    )
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return normalize_aware_utc(value) if value is not None else None


class InternalVersionRecord(InternalVersionSummary):
    fields: list[CandidateFieldRecord]
    diff: list[FieldDiff]


class InternalVersionList(StrictModel):
    program_id: Identifier
    versions: list[InternalVersionSummary]


class InternalVersionDiff(StrictModel):
    version_id: Identifier
    base_version_id: Identifier | None
    diff: list[FieldDiff]


class AuditEventRecord(StrictModel):
    id: Identifier
    program_id: Identifier
    version_id: Identifier | None
    event_type: AuditEventType
    actor_ref: ActorRef
    actor_role: ActorRole
    reason: str | None
    request_id: Identifier
    idempotency_key_hash: Sha256Hex | None
    event_payload: dict[str, Any]
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


class AuditTimelineRecord(StrictModel):
    program_id: Identifier
    events: list[AuditEventRecord]
