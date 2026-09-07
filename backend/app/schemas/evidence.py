from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, RootModel, field_validator, model_validator

from backend.app.db.models import EvidenceAvailability, SourceType
from backend.app.schemas.profile_analysis import StrictModel


Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")]
ActorRef = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,119}$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class EvidenceFreshness(StrEnum):
    FRESH = "fresh"
    REVIEW_DUE = "review_due"
    EXPIRED = "expired"
    SOURCE_UNAVAILABLE = "source_unavailable"


class EvidenceCaptureMethod(StrEnum):
    MANUAL_BROWSER = "manual_browser"
    MANUAL_PDF = "manual_pdf"
    AUTOMATED_WEB_CANDIDATE = "automated_web_candidate"


class EvidenceHashScope(StrEnum):
    NORMALIZED_EXCERPT = "normalized_excerpt"
    FULL_DOCUMENT_BYTES = "full_document_bytes"


class ReviewedSourceRole(StrEnum):
    PROGRAM = "program"
    ADMISSIONS_POLICY = "admissions_policy"
    LANGUAGE_POLICY = "language_policy"
    CURRICULUM = "curriculum"
    SCOPE_NOTICE = "scope_notice"


def normalize_official_domain(value: str) -> str:
    candidate = value.strip().rstrip(".").lower()
    if not candidate or len(candidate) > 253:
        raise ValueError("official_domain is invalid")
    try:
        ascii_domain = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("official_domain is invalid") from exc
    labels = ascii_domain.split(".")
    if len(labels) < 2 or any(
        not label
        or len(label) > 63
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
        for label in labels
    ):
        raise ValueError("official_domain is invalid")
    return ascii_domain


def normalize_official_domain_aliases(
    values: Sequence[str], *, registered_domain: str
) -> list[str]:
    registered = normalize_official_domain(registered_domain)
    normalized = [normalize_official_domain(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError("official_domain_aliases cannot contain duplicates")
    if registered in normalized:
        raise ValueError(
            "official_domain_aliases cannot repeat registered_official_domain"
        )
    roots = [registered, *normalized]
    if any(
        left.endswith(f".{right}") or right.endswith(f".{left}")
        for index, left in enumerate(roots)
        for right in roots[index + 1 :]
    ):
        raise ValueError("official domain roots and aliases cannot overlap")
    return sorted(normalized)


def belongs_to_official_domains(
    domain: str, *, registered_domain: str, aliases: Sequence[str] = ()
) -> bool:
    normalized_domain = normalize_official_domain(domain)
    allowed = {
        normalize_official_domain(registered_domain),
        *(normalize_official_domain(alias) for alias in aliases),
    }
    return any(
        normalized_domain == root or normalized_domain.endswith(f".{root}")
        for root in allowed
    )


def normalize_official_url(value: str) -> str:
    if any(ord(character) < 32 for character in value):
        raise ValueError("source URL contains control characters")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("source URL is invalid") from exc
    if parsed.scheme.lower() != "https":
        raise ValueError("source URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source URL must not contain credentials")
    if parsed.hostname is None:
        raise ValueError("source URL must contain a host")
    if port not in {None, 443}:
        raise ValueError("source URL must not use a non-standard port")

    host = normalize_official_domain(parsed.hostname)
    netloc = host if port is None else f"{host}:443"
    path = parsed.path or "/"
    normalized_query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit(("https", netloc, path, normalized_query, ""))


def normalize_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


class SourceEvidenceCreate(StrictModel):
    id: Identifier
    program_id: Identifier
    source_type: SourceType
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    official_domain: Annotated[str, Field(min_length=3, max_length=253)]
    page_title: Annotated[str, Field(min_length=1, max_length=500)]
    excerpt: Annotated[str, Field(min_length=1, max_length=4000)]
    snapshot_sha256: Sha256Hex
    source_version: Annotated[str, Field(min_length=1, max_length=200)]
    captured_at: datetime
    verified_at: datetime
    verified_by: ActorRef
    review_due_at: datetime
    expires_at: datetime
    availability_at_verification: EvidenceAvailability

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_official_url(value)

    @field_validator("official_domain")
    @classmethod
    def validate_official_domain(cls, value: str) -> str:
        return normalize_official_domain(value)

    @field_validator(
        "captured_at", "verified_at", "review_due_at", "expires_at", mode="after"
    )
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)

    @model_validator(mode="after")
    def validate_source_contract(self) -> "SourceEvidenceCreate":
        host = normalize_official_domain(urlsplit(self.url).hostname or "")
        if host != self.official_domain:
            raise ValueError("official_domain must equal the normalized URL host")
        if self.verified_at < self.captured_at:
            raise ValueError("verified_at cannot be before captured_at")
        if self.review_due_at <= self.verified_at:
            raise ValueError("review_due_at must be after verified_at")
        if self.expires_at <= self.review_due_at:
            raise ValueError("expires_at must be after review_due_at")
        return self


class SourceEvidenceRecord(SourceEvidenceCreate):
    created_at: datetime
    freshness: EvidenceFreshness

    @field_validator("created_at", mode="after")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


class SourceEvidenceCreateV2(SourceEvidenceCreate):
    schema_version: Literal["source_evidence.v2"]
    capture_method: EvidenceCaptureMethod
    hash_scope: EvidenceHashScope
    reviewed_source_role: ReviewedSourceRole


class SourceEvidenceRecordV2(SourceEvidenceCreateV2):
    created_at: datetime
    freshness: EvidenceFreshness

    @field_validator("created_at", mode="after")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)


SourceEvidenceCreateAny: TypeAlias = SourceEvidenceCreateV2 | SourceEvidenceCreate
SourceEvidenceRecordAny: TypeAlias = SourceEvidenceRecordV2 | SourceEvidenceRecord


class SourceEvidenceRecordEnvelope(RootModel[SourceEvidenceRecordAny]):
    pass


def derive_evidence_freshness(
    *,
    availability: EvidenceAvailability | str,
    review_due_at: datetime,
    expires_at: datetime,
    now: datetime,
) -> EvidenceFreshness:
    current_time = normalize_aware_utc(now)
    review_due = normalize_aware_utc(review_due_at)
    expiry = normalize_aware_utc(expires_at)
    if availability == EvidenceAvailability.SOURCE_UNAVAILABLE:
        return EvidenceFreshness.SOURCE_UNAVAILABLE
    if current_time >= expiry:
        return EvidenceFreshness.EXPIRED
    if current_time >= review_due:
        return EvidenceFreshness.REVIEW_DUE
    return EvidenceFreshness.FRESH
