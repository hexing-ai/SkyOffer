"""allow automated web candidate evidence capture

Revision ID: 20260904_0004
Revises: 20260903_0003
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op


revision = "20260904_0004"
down_revision = "20260903_0003"
branch_labels = None
depends_on = None


_INSERT_TRIGGER = """
CREATE TRIGGER source_evidence_v2_validate_insert
BEFORE INSERT ON source_evidence WHEN
NOT (NEW.capture_method IS NULL AND NEW.hash_scope IS NULL
AND NEW.reviewed_source_role IS NULL) AND
(NEW.capture_method IS NULL OR NEW.hash_scope IS NULL
OR NEW.reviewed_source_role IS NULL
OR NEW.capture_method NOT IN
('manual_browser', 'manual_pdf', 'automated_web_candidate')
OR NEW.hash_scope NOT IN ('normalized_excerpt', 'full_document_bytes')
OR NEW.reviewed_source_role NOT IN
('program', 'admissions_policy', 'language_policy', 'curriculum', 'scope_notice'))
BEGIN SELECT RAISE(ABORT, 'invalid Evidence V2 metadata'); END
"""

_UPDATE_TRIGGER = _INSERT_TRIGGER.replace(
    "source_evidence_v2_validate_insert\nBEFORE INSERT",
    "source_evidence_v2_validate_update\nBEFORE UPDATE",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER source_evidence_v2_validate_update")
        op.execute("DROP TRIGGER source_evidence_v2_validate_insert")
        op.execute(_INSERT_TRIGGER)
        op.execute(_UPDATE_TRIGGER)
    else:
        op.drop_constraint(
            "capture_method_allowed", "source_evidence", type_="check"
        )
        op.create_check_constraint(
            "capture_method_allowed",
            "source_evidence",
            "capture_method IS NULL OR capture_method IN "
            "('manual_browser', 'manual_pdf', 'automated_web_candidate')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER source_evidence_v2_validate_update")
        op.execute("DROP TRIGGER source_evidence_v2_validate_insert")
        op.execute(
            _INSERT_TRIGGER.replace(
                ", 'automated_web_candidate'", ""
            )
        )
        op.execute(
            _UPDATE_TRIGGER.replace(
                ", 'automated_web_candidate'", ""
            )
        )
    else:
        op.drop_constraint(
            "capture_method_allowed", "source_evidence", type_="check"
        )
        op.create_check_constraint(
            "capture_method_allowed",
            "source_evidence",
            "capture_method IS NULL OR capture_method IN "
            "('manual_browser', 'manual_pdf')",
        )
