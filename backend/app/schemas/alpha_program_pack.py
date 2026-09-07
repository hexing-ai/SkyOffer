from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from backend.app.db.models import ProgramRegion
from backend.app.schemas.candidates import CandidateCreate
from backend.app.schemas.evidence import (
    ActorRef,
    Identifier,
    Sha256Hex,
    SourceEvidenceCreateV2,
    normalize_aware_utc,
    normalize_official_domain,
    normalize_official_domain_aliases,
    normalize_official_url,
)
from backend.app.schemas.profile_analysis import StrictModel


class AlphaPackProgramCreate(StrictModel):
    program_ref: Identifier
    official_name: Annotated[str, Field(min_length=1, max_length=300)]
    institution_name: Annotated[str, Field(min_length=1, max_length=300)]
    region: ProgramRegion
    official_program_url: Annotated[str, Field(min_length=1, max_length=2048)]
    registered_official_domain: Annotated[str, Field(min_length=3, max_length=253)]
    official_domain_aliases: Annotated[list[str], Field(max_length=10)] = Field(
        default_factory=list
    )
    degree_type: Literal["taught_masters"]
    created_by: Literal["actor.data_preparer.codex"]
    creation_note: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("official_program_url")
    @classmethod
    def normalize_program_url(cls, value: str) -> str:
        return normalize_official_url(value)

    @field_validator("registered_official_domain")
    @classmethod
    def normalize_registered_domain(cls, value: str) -> str:
        return normalize_official_domain(value)

    @model_validator(mode="after")
    def validate_program_domain(self) -> "AlphaPackProgramCreate":
        self.official_domain_aliases = normalize_official_domain_aliases(
            self.official_domain_aliases,
            registered_domain=self.registered_official_domain,
        )
        host = normalize_official_domain(
            urlsplit(self.official_program_url).hostname or ""
        )
        if host != self.registered_official_domain and not host.endswith(
            f".{self.registered_official_domain}"
        ):
            raise ValueError(
                "official_program_url must belong to registered_official_domain"
            )
        return self


class AlphaPackReview(StrictModel):
    prepared_by: Literal["actor.data_preparer.codex"]
    prepared_at: datetime
    reviewed_by: Literal["actor.domain_reviewer.product_owner"]
    reviewed_at: datetime
    review_note: Annotated[str, Field(min_length=1, max_length=1000)]
    review_status: Literal["approved"]

    @field_validator("prepared_at", "reviewed_at", mode="after")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)

    @model_validator(mode="after")
    def validate_four_eye_review(self) -> "AlphaPackReview":
        if self.prepared_by == self.reviewed_by:
            raise ValueError("data preparer and domain reviewer must be different")
        if self.reviewed_at < self.prepared_at:
            raise ValueError("reviewed_at cannot be before prepared_at")
        return self


class AlphaPackEvidenceV2(SourceEvidenceCreateV2):
    applicable_academic_year: Literal["2027-28"]


class AlphaProgramPackV1(StrictModel):
    schema_version: Literal["alpha_program_pack.v1"]
    pack_ref: Identifier
    scope_snapshot_id: Identifier
    scope_institution_ref: Identifier
    target_academic_year: Literal["2027-28"]
    program: AlphaPackProgramCreate
    reviewed_source_ids: Annotated[list[Identifier], Field(min_length=1, max_length=50)]
    evidence: Annotated[list[AlphaPackEvidenceV2], Field(min_length=1, max_length=50)]
    candidate: CandidateCreate
    review: AlphaPackReview
    pack_canonical_sha256: Sha256Hex
    expected_semantic_content_sha256: Sha256Hex

    @model_validator(mode="after")
    def normalize_identity_sets(self) -> "AlphaProgramPackV1":
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("pack evidence IDs cannot contain duplicates")
        if len(self.reviewed_source_ids) != len(set(self.reviewed_source_ids)):
            raise ValueError("reviewed_source_ids cannot contain duplicates")
        if set(evidence_ids) != set(self.reviewed_source_ids):
            raise ValueError(
                "reviewed_source_ids must exactly match the pack Evidence V2 set"
            )
        if self.program.created_by != self.review.prepared_by:
            raise ValueError("program creator must equal pack data preparer")
        if self.candidate.created_by != self.review.prepared_by:
            raise ValueError("candidate creator must equal pack data preparer")
        if self.candidate.base_version_id is not None:
            raise ValueError("alpha program pack candidate must not claim a base version")
        self.reviewed_source_ids = sorted(self.reviewed_source_ids)
        self.evidence = sorted(self.evidence, key=lambda item: item.id)
        return self
