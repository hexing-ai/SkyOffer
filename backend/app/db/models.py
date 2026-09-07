from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.db.types import UTCDateTime


class ProgramRegion(StrEnum):
    HONG_KONG = "hong_kong"
    UNITED_KINGDOM = "united_kingdom"


class SourceType(StrEnum):
    OFFICIAL_PROGRAM_PAGE = "official_program_page"
    OFFICIAL_POLICY_PAGE = "official_policy_page"
    OFFICIAL_PDF = "official_pdf"
    OFFICIAL_NOTICE = "official_notice"


class EvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    SOURCE_UNAVAILABLE = "source_unavailable"


class VersionStatus(StrEnum):
    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class EvidenceSupportScope(StrEnum):
    DIRECT = "direct"
    APPLICABILITY = "applicability"
    DEFINITION = "definition"
    COVERAGE = "coverage"


class AuditEventType(StrEnum):
    CREATE = "create"
    SUBMIT = "submit"
    PUBLISH = "publish"
    REJECT = "reject"
    ROLLBACK_CANDIDATE_CREATED = "rollback_candidate_created"


class ActorRole(StrEnum):
    DATA_PREPARER = "data_preparer"
    DOMAIN_REVIEWER = "domain_reviewer"
    SYSTEM = "system"


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        CheckConstraint(
            "region IN ('hong_kong', 'united_kingdom')", name="region_allowed"
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    official_name: Mapped[str] = mapped_column(String(300), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(300), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    official_program_url: Mapped[str] = mapped_column(Text, nullable=False)
    registered_official_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    official_domain_aliases: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    evidence: Mapped[list[SourceEvidence]] = relationship(
        back_populates="program", passive_deletes=True
    )
    versions: Mapped[list[ProgramVersion]] = relationship(
        back_populates="program", passive_deletes=True
    )
    publication: Mapped[ProgramPublication | None] = relationship(
        back_populates="program", uselist=False, passive_deletes=True
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="program", passive_deletes=True
    )


class SourceEvidence(Base):
    __tablename__ = "source_evidence"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('official_program_page', 'official_policy_page', "
            "'official_pdf', 'official_notice')",
            name="source_type_allowed",
        ),
        CheckConstraint(
            "availability_at_verification IN ('available', 'source_unavailable')",
            name="availability_allowed",
        ),
        CheckConstraint("length(snapshot_sha256) = 64", name="snapshot_hash_length"),
        CheckConstraint("expires_at > review_due_at", name="freshness_order"),
        CheckConstraint(
            "(capture_method IS NULL AND hash_scope IS NULL AND reviewed_source_role IS NULL) "
            "OR (capture_method IS NOT NULL AND hash_scope IS NOT NULL "
            "AND reviewed_source_role IS NOT NULL)",
            name="evidence_v2_metadata_complete",
        ),
        CheckConstraint(
            "capture_method IS NULL OR capture_method IN "
            "('manual_browser', 'manual_pdf', 'automated_web_candidate')",
            name="capture_method_allowed",
        ),
        CheckConstraint(
            "hash_scope IS NULL OR hash_scope IN ('normalized_excerpt', 'full_document_bytes')",
            name="hash_scope_allowed",
        ),
        CheckConstraint(
            "reviewed_source_role IS NULL OR reviewed_source_role IN "
            "('program', 'admissions_policy', 'language_policy', 'curriculum', 'scope_notice')",
            name="reviewed_source_role_allowed",
        ),
        UniqueConstraint("id", "program_id", name="uq_source_evidence_id_program_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    official_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    page_title: Mapped[str] = mapped_column(String(500), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str] = mapped_column(String(200), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    verified_by: Mapped[str] = mapped_column(String(120), nullable=False)
    review_due_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    availability_at_verification: Mapped[str] = mapped_column(String(32), nullable=False)
    capture_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hash_scope: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_source_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    program: Mapped[Program] = relationship(back_populates="evidence")
    field_links: Mapped[list[FieldEvidenceLink]] = relationship(
        back_populates="evidence", passive_deletes=True
    )


class ProgramVersion(Base):
    __tablename__ = "program_versions"
    __table_args__ = (
        CheckConstraint("version_no > 0", name="version_no_positive"),
        CheckConstraint(
            "status IN ('candidate', 'pending_review', 'published', 'rejected', "
            "'superseded')",
            name="status_allowed",
        ),
        CheckConstraint("length(content_sha256) = 64", name="content_hash_length"),
        UniqueConstraint("program_id", "version_no", name="uq_program_versions_program_version"),
        UniqueConstraint("id", "program_id", name="uq_program_versions_id_program_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    base_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("program_versions.id", ondelete="RESTRICT"), nullable=True
    )
    rollback_of_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("program_versions.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    content_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    program: Mapped[Program] = relationship(back_populates="versions", foreign_keys=[program_id])
    field_values: Mapped[list[ProgramFieldValue]] = relationship(
        back_populates="program_version", passive_deletes=True
    )


class ProgramFieldValue(Base):
    __tablename__ = "program_field_values"
    __table_args__ = (
        CheckConstraint("length(value_sha256) = 64", name="value_hash_length"),
        UniqueConstraint(
            "program_version_id",
            "field_key",
            name="uq_program_field_values_version_field_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    program_version_id: Mapped[str] = mapped_column(
        ForeignKey("program_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    value_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    display_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    value_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    program_version: Mapped[ProgramVersion] = relationship(back_populates="field_values")
    evidence_links: Mapped[list[FieldEvidenceLink]] = relationship(
        back_populates="field_value", passive_deletes=True
    )


class FieldEvidenceLink(Base):
    __tablename__ = "field_evidence_links"
    __table_args__ = (
        CheckConstraint(
            "support_scope IN ('direct', 'applicability', 'definition', 'coverage')",
            name="support_scope_allowed",
        ),
        CheckConstraint("citation_order > 0", name="citation_order_positive"),
        UniqueConstraint(
            "field_value_id",
            "citation_order",
            name="uq_field_evidence_links_field_citation_order",
        ),
    )

    field_value_id: Mapped[str] = mapped_column(
        ForeignKey("program_field_values.id", ondelete="RESTRICT"), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(
        ForeignKey("source_evidence.id", ondelete="RESTRICT"), primary_key=True
    )
    support_scope: Mapped[str] = mapped_column(String(24), nullable=False)
    citation_order: Mapped[int] = mapped_column(Integer, nullable=False)

    field_value: Mapped[ProgramFieldValue] = relationship(back_populates="evidence_links")
    evidence: Mapped[SourceEvidence] = relationship(back_populates="field_links")


class ProgramPublication(Base):
    __tablename__ = "program_publications"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="revision_non_negative"),
        UniqueConstraint("current_version_id", name="uq_program_publications_current_version_id"),
    )

    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), primary_key=True
    )
    current_version_id: Mapped[str] = mapped_column(
        ForeignKey("program_versions.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    program: Mapped[Program] = relationship(back_populates="publication", foreign_keys=[program_id])
    current_version: Mapped[ProgramVersion] = relationship(foreign_keys=[current_version_id])


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('create', 'submit', 'publish', 'reject', "
            "'rollback_candidate_created')",
            name="event_type_allowed",
        ),
        CheckConstraint(
            "actor_role IN ('data_preparer', 'domain_reviewer', 'system')",
            name="actor_role_allowed",
        ),
        CheckConstraint(
            "idempotency_key_hash IS NULL OR length(idempotency_key_hash) = 64",
            name="idempotency_hash_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_id: Mapped[str | None] = mapped_column(
        ForeignKey("program_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    program: Mapped[Program] = relationship(back_populates="audit_events")
    version: Mapped[ProgramVersion | None] = relationship(foreign_keys=[version_id])


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("length(key_hash) = 64", name="key_hash_length"),
        CheckConstraint("length(request_sha256) = 64", name="request_hash_length"),
        CheckConstraint(
            "response_status BETWEEN 100 AND 599", name="response_status_valid"
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    operation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
