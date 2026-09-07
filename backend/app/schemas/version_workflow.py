from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator

from backend.app.db.models import VersionStatus
from backend.app.schemas.evidence import ActorRef, Identifier, normalize_aware_utc
from backend.app.schemas.profile_analysis import StrictModel


ReviewNote = Annotated[str, Field(min_length=1, max_length=1000)]


class SubmitVersionCommand(StrictModel):
    submitted_by: ActorRef
    submission_note: ReviewNote
    request_id: Identifier


class ReviewVersionCommand(StrictModel):
    reviewed_by: ActorRef
    review_note: ReviewNote
    request_id: Identifier


class PublishVersionCommand(ReviewVersionCommand):
    expected_current_version_id: Identifier | None = None


class VersionTransitionRecord(StrictModel):
    version_id: Identifier
    program_id: Identifier
    status: VersionStatus
    submitted_by: ActorRef | None
    reviewed_by: ActorRef | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    published_at: datetime | None
    current_version_id: Identifier | None
    publication_revision: int | None

    @field_validator("submitted_at", "reviewed_at", "published_at", mode="after")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return normalize_aware_utc(value) if value is not None else None
