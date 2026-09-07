"""phase 4 schema compatibility

Revision ID: 20260902_0002
Revises: 20260901_0001
Create Date: 2026-09-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260902_0002"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_evidence", sa.Column("capture_method", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "source_evidence", sa.Column("hash_scope", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "source_evidence",
        sa.Column("reviewed_source_role", sa.String(length=32), nullable=True),
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER source_evidence_v2_validate_insert "
            "BEFORE INSERT ON source_evidence WHEN "
            "NOT (NEW.capture_method IS NULL AND NEW.hash_scope IS NULL "
            "AND NEW.reviewed_source_role IS NULL) AND "
            "(NEW.capture_method IS NULL OR NEW.hash_scope IS NULL "
            "OR NEW.reviewed_source_role IS NULL "
            "OR NEW.capture_method NOT IN ('manual_browser', 'manual_pdf') "
            "OR NEW.hash_scope NOT IN ('normalized_excerpt', 'full_document_bytes') "
            "OR NEW.reviewed_source_role NOT IN ('program', 'admissions_policy', "
            "'language_policy', 'curriculum', 'scope_notice')) "
            "BEGIN SELECT RAISE(ABORT, 'invalid Evidence V2 metadata'); END"
        )
        op.execute(
            "CREATE TRIGGER source_evidence_v2_validate_update "
            "BEFORE UPDATE ON source_evidence WHEN "
            "NOT (NEW.capture_method IS NULL AND NEW.hash_scope IS NULL "
            "AND NEW.reviewed_source_role IS NULL) AND "
            "(NEW.capture_method IS NULL OR NEW.hash_scope IS NULL "
            "OR NEW.reviewed_source_role IS NULL "
            "OR NEW.capture_method NOT IN ('manual_browser', 'manual_pdf') "
            "OR NEW.hash_scope NOT IN ('normalized_excerpt', 'full_document_bytes') "
            "OR NEW.reviewed_source_role NOT IN ('program', 'admissions_policy', "
            "'language_policy', 'curriculum', 'scope_notice')) "
            "BEGIN SELECT RAISE(ABORT, 'invalid Evidence V2 metadata'); END"
        )
    else:
        op.create_check_constraint(
            "evidence_v2_metadata_complete",
            "source_evidence",
            "(capture_method IS NULL AND hash_scope IS NULL AND reviewed_source_role IS NULL) "
            "OR (capture_method IS NOT NULL AND hash_scope IS NOT NULL "
            "AND reviewed_source_role IS NOT NULL)",
        )
        op.create_check_constraint(
            "capture_method_allowed",
            "source_evidence",
            "capture_method IS NULL OR capture_method IN ('manual_browser', 'manual_pdf')",
        )
        op.create_check_constraint(
            "hash_scope_allowed",
            "source_evidence",
            "hash_scope IS NULL OR hash_scope IN ('normalized_excerpt', 'full_document_bytes')",
        )
        op.create_check_constraint(
            "reviewed_source_role_allowed",
            "source_evidence",
            "reviewed_source_role IS NULL OR reviewed_source_role IN "
            "('program', 'admissions_policy', 'language_policy', 'curriculum', 'scope_notice')",
        )

    with op.batch_alter_table("field_evidence_links") as batch_op:
        batch_op.drop_constraint("support_scope_allowed", type_="check")
        batch_op.create_check_constraint(
            "support_scope_allowed",
            "support_scope IN ('direct', 'applicability', 'definition', 'coverage')",
        )


def downgrade() -> None:
    with op.batch_alter_table("field_evidence_links") as batch_op:
        batch_op.drop_constraint("support_scope_allowed", type_="check")
        batch_op.create_check_constraint(
            "support_scope_allowed",
            "support_scope IN ('direct', 'applicability', 'definition')",
        )

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER source_evidence_v2_validate_update")
        op.execute("DROP TRIGGER source_evidence_v2_validate_insert")
    else:
        op.drop_constraint(
            "reviewed_source_role_allowed", "source_evidence", type_="check"
        )
        op.drop_constraint("hash_scope_allowed", "source_evidence", type_="check")
        op.drop_constraint("capture_method_allowed", "source_evidence", type_="check")
        op.drop_constraint(
            "evidence_v2_metadata_complete", "source_evidence", type_="check"
        )
    op.drop_column("source_evidence", "reviewed_source_role")
    op.drop_column("source_evidence", "hash_scope")
    op.drop_column("source_evidence", "capture_method")
