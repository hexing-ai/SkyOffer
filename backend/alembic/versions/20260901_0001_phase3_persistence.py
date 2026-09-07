"""Create the Phase 3 evidence and version persistence schema.

Revision ID: 20260901_0001
Revises:
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260901_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("operation_type", sa.String(length=80), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(key_hash) = 64", name=op.f("ck_idempotency_records_key_hash_length")
        ),
        sa.CheckConstraint(
            "length(request_sha256) = 64",
            name=op.f("ck_idempotency_records_request_hash_length"),
        ),
        sa.CheckConstraint(
            "response_status BETWEEN 100 AND 599",
            name=op.f("ck_idempotency_records_response_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
        sa.UniqueConstraint("key_hash", name="uq_idempotency_records_key_hash"),
    )
    op.create_table(
        "programs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("official_name", sa.String(length=300), nullable=False),
        sa.Column("institution_name", sa.String(length=300), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=False),
        sa.Column("official_program_url", sa.Text(), nullable=False),
        sa.Column("registered_official_domain", sa.String(length=253), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "region IN ('hong_kong', 'united_kingdom')",
            name=op.f("ck_programs_region_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_programs"),
    )
    op.create_table(
        "program_versions",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("program_id", sa.String(length=80), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("base_version_id", sa.String(length=80), nullable=True),
        sa.Column("rollback_of_version_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_schema_version", sa.String(length=80), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("submitted_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(content_sha256) = 64",
            name=op.f("ck_program_versions_content_hash_length"),
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'pending_review', 'published', 'rejected', 'superseded')",
            name=op.f("ck_program_versions_status_allowed"),
        ),
        sa.CheckConstraint(
            "version_no > 0", name=op.f("ck_program_versions_version_no_positive")
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id"],
            ["program_versions.id"],
            name="fk_program_versions_base_version_id_program_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_program_versions_program_id_programs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_of_version_id"],
            ["program_versions.id"],
            name="fk_program_versions_rollback_of_version_id_program_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_program_versions"),
        sa.UniqueConstraint("id", "program_id", name="uq_program_versions_id_program_id"),
        sa.UniqueConstraint(
            "program_id", "version_no", name="uq_program_versions_program_version"
        ),
    )
    op.create_index(
        op.f("ix_program_versions_program_id"), "program_versions", ["program_id"], unique=False
    )
    op.create_table(
        "source_evidence",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("program_id", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("official_domain", sa.String(length=253), nullable=False),
        sa.Column("page_title", sa.String(length=500), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.String(length=200), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by", sa.String(length=120), nullable=False),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("availability_at_verification", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "availability_at_verification IN ('available', 'source_unavailable')",
            name=op.f("ck_source_evidence_availability_allowed"),
        ),
        sa.CheckConstraint(
            "expires_at > review_due_at",
            name=op.f("ck_source_evidence_freshness_order"),
        ),
        sa.CheckConstraint(
            "length(snapshot_sha256) = 64",
            name=op.f("ck_source_evidence_snapshot_hash_length"),
        ),
        sa.CheckConstraint(
            "source_type IN ('official_program_page', 'official_policy_page', 'official_pdf', 'official_notice')",
            name=op.f("ck_source_evidence_source_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_source_evidence_program_id_programs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_evidence"),
        sa.UniqueConstraint("id", "program_id", name="uq_source_evidence_id_program_id"),
    )
    op.create_index(
        op.f("ix_source_evidence_program_id"), "source_evidence", ["program_id"], unique=False
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("program_id", sa.String(length=80), nullable=False),
        sa.Column("version_id", sa.String(length=80), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_ref", sa.String(length=120), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_role IN ('data_preparer', 'domain_reviewer', 'system')",
            name=op.f("ck_audit_events_actor_role_allowed"),
        ),
        sa.CheckConstraint(
            "event_type IN ('create', 'submit', 'publish', 'reject', 'rollback_candidate_created')",
            name=op.f("ck_audit_events_event_type_allowed"),
        ),
        sa.CheckConstraint(
            "idempotency_key_hash IS NULL OR length(idempotency_key_hash) = 64",
            name=op.f("ck_audit_events_idempotency_hash_length"),
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_audit_events_program_id_programs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["program_versions.id"],
            name="fk_audit_events_version_id_program_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(op.f("ix_audit_events_program_id"), "audit_events", ["program_id"], unique=False)
    op.create_index(op.f("ix_audit_events_version_id"), "audit_events", ["version_id"], unique=False)
    op.create_table(
        "program_field_values",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("program_version_id", sa.String(length=80), nullable=False),
        sa.Column("field_key", sa.String(length=120), nullable=False),
        sa.Column("value_schema_version", sa.String(length=80), nullable=False),
        sa.Column("value_payload", sa.JSON(), nullable=False),
        sa.Column("display_text", sa.Text(), nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.Column("value_sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "length(value_sha256) = 64",
            name=op.f("ck_program_field_values_value_hash_length"),
        ),
        sa.ForeignKeyConstraint(
            ["program_version_id"],
            ["program_versions.id"],
            name="fk_program_field_values_program_version_id_program_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_program_field_values"),
        sa.UniqueConstraint(
            "program_version_id",
            "field_key",
            name="uq_program_field_values_version_field_key",
        ),
    )
    op.create_index(
        op.f("ix_program_field_values_program_version_id"),
        "program_field_values",
        ["program_version_id"],
        unique=False,
    )
    op.create_table(
        "program_publications",
        sa.Column("program_id", sa.String(length=80), nullable=False),
        sa.Column("current_version_id", sa.String(length=80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision >= 0",
            name=op.f("ck_program_publications_revision_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["current_version_id"],
            ["program_versions.id"],
            name="fk_program_publications_current_version_id_program_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["programs.id"],
            name="fk_program_publications_program_id_programs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("program_id", name="pk_program_publications"),
        sa.UniqueConstraint(
            "current_version_id", name="uq_program_publications_current_version_id"
        ),
    )
    op.create_table(
        "field_evidence_links",
        sa.Column("field_value_id", sa.String(length=80), nullable=False),
        sa.Column("evidence_id", sa.String(length=80), nullable=False),
        sa.Column("support_scope", sa.String(length=24), nullable=False),
        sa.Column("citation_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "citation_order > 0",
            name=op.f("ck_field_evidence_links_citation_order_positive"),
        ),
        sa.CheckConstraint(
            "support_scope IN ('direct', 'applicability', 'definition')",
            name=op.f("ck_field_evidence_links_support_scope_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["source_evidence.id"],
            name="fk_field_evidence_links_evidence_id_source_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["field_value_id"],
            ["program_field_values.id"],
            name="fk_field_evidence_links_field_value_id_program_field_values",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "field_value_id", "evidence_id", name="pk_field_evidence_links"
        ),
        sa.UniqueConstraint(
            "field_value_id",
            "citation_order",
            name="uq_field_evidence_links_field_citation_order",
        ),
    )


def downgrade() -> None:
    op.drop_table("field_evidence_links")
    op.drop_table("program_publications")
    op.drop_index(op.f("ix_program_field_values_program_version_id"), table_name="program_field_values")
    op.drop_table("program_field_values")
    op.drop_index(op.f("ix_audit_events_version_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_program_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_source_evidence_program_id"), table_name="source_evidence")
    op.drop_table("source_evidence")
    op.drop_index(op.f("ix_program_versions_program_id"), table_name="program_versions")
    op.drop_table("program_versions")
    op.drop_table("programs")
    op.drop_table("idempotency_records")
