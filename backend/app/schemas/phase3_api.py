from __future__ import annotations

from typing import Annotated

from pydantic import Field

from backend.app.schemas.candidates import CandidateFieldCreate
from backend.app.schemas.evidence import ActorRef, Identifier, SourceEvidenceRecordAny
from backend.app.schemas.profile_analysis import StrictModel


Note = Annotated[str, Field(min_length=1, max_length=1000)]


class CandidateCreateRequest(StrictModel):
    base_version_id: Identifier | None = None
    fields: Annotated[list[CandidateFieldCreate], Field(max_length=100)]
    created_by: ActorRef
    creation_note: Note


class SubmitVersionRequest(StrictModel):
    submitted_by: ActorRef
    submission_note: Note


class PublishVersionRequest(StrictModel):
    reviewed_by: ActorRef
    review_note: Note
    expected_current_version_id: Identifier | None = None


class RejectVersionRequest(StrictModel):
    reviewed_by: ActorRef
    review_note: Note


class RollbackCandidateRequest(StrictModel):
    target_version_id: Identifier
    expected_current_version_id: Identifier
    created_by: ActorRef
    creation_note: Note


class SourceEvidenceList(StrictModel):
    program_id: Identifier
    evidence: list[SourceEvidenceRecordAny]
