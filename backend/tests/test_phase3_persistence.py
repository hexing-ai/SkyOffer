from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.db.base import Base
from backend.app.db.migrations import (
    DatabaseRevisionError,
    assert_database_at_head,
    current_database_revision,
    expected_head_revision,
    upgrade_database,
)
from backend.app.db.models import (
    ActorRole,
    AuditEvent,
    AuditEventType,
    EvidenceAvailability,
    EvidenceSupportScope,
    FieldEvidenceLink,
    IdempotencyRecord,
    Program,
    ProgramFieldValue,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    SourceEvidence,
    SourceType,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory


PILOT_PROGRAM_ID = "program.pilot.edinburgh.computer_science_msc"
PILOT_VERSION_ID = "version.pilot.edinburgh.v1"
PILOT_FIELD_ID = "field.pilot.edinburgh.ielts.v1"
PILOT_EVIDENCE_ID = "evidence.pilot.edinburgh.cs.ielts.2026_27"
POLICY_EVIDENCE_ID = "evidence.pilot.edinburgh.english_policy.2026"
FIXED_NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'phase3.sqlite3'}"


def test_upgrade_creates_missing_sqlite_parent_directory(tmp_path) -> None:
    nested_database = tmp_path / "new" / "nested" / "phase3.sqlite3"
    url = f"sqlite:///{nested_database}"

    assert not nested_database.parent.exists()
    upgrade_database(url)

    engine = create_database_engine(url)
    assert_database_at_head(engine)
    engine.dispose()
    assert nested_database.is_file()


def test_alembic_schema_matches_models_and_enables_foreign_keys(tmp_path) -> None:
    url = database_url(tmp_path)
    engine = create_database_engine(url)

    with pytest.raises(DatabaseRevisionError, match="数据库版本不匹配"):
        assert_database_at_head(engine)
    engine.dispose()

    upgrade_database(url)
    upgrade_database(url)

    engine = create_database_engine(url)
    assert current_database_revision(engine) == expected_head_revision()
    assert_database_at_head(engine)

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        migration_context = MigrationContext.configure(
            connection, opts={"compare_type": True}
        )
        assert compare_metadata(migration_context, Base.metadata) == []

    engine.dispose()


def test_published_evidence_graph_survives_engine_restart(tmp_path) -> None:
    url = database_url(tmp_path)
    upgrade_database(url)

    first_engine = create_database_engine(url)
    first_sessions = create_session_factory(first_engine)
    review_due = FIXED_NOW + timedelta(days=30)
    expires = review_due + timedelta(days=7)
    value_payload = {
        "schema_version": "program_requirement_field.v1",
        "applicable_academic_year": "2026-27",
        "coverage": "score_threshold_only",
        "requirement": {
            "requirement_id": "requirement.pilot.ielts",
            "requirement_type": "language",
            "is_hard": True,
            "applicability": None,
            "rule": {
                "node_id": "node.pilot.ielts.minimum",
                "operator": "language_minimum",
                "test_type": "ielts",
                "total_min": "7.0",
                "component_mins": {
                    "listening": "6.5",
                    "reading": "6.5",
                    "speaking": "6.5",
                    "writing": "6.5",
                },
            },
            "evidence_fixture_ids": [PILOT_EVIDENCE_ID, POLICY_EVIDENCE_ID],
            "display_text": "2026–27 IELTS Academic：总分至少 7.0，各项至少 6.5。",
        },
    }

    with first_sessions.begin() as session:
        session.add(
            Program(
                id=PILOT_PROGRAM_ID,
                official_name="Computer Science MSc",
                institution_name="The University of Edinburgh",
                region=ProgramRegion.UNITED_KINGDOM,
                official_program_url=(
                    "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science"
                ),
                registered_official_domain="ed.ac.uk",
                created_at=FIXED_NOW,
            )
        )
        session.add_all(
            [
                SourceEvidence(
                    id=PILOT_EVIDENCE_ID,
                    program_id=PILOT_PROGRAM_ID,
                    source_type=SourceType.OFFICIAL_PROGRAM_PAGE,
                    url=(
                        "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science"
                    ),
                    official_domain="study.ed.ac.uk",
                    page_title=(
                        "Computer Science MSc - Postgraduate taught programmes | "
                        "The University of Edinburgh"
                    ),
                    excerpt=(
                        "IELTS Academic: total 7.0 with at least 6.5 in each component "
                        "We do not accept IELTS One Skill Retake to meet our English "
                        "language requirements."
                    ),
                    snapshot_sha256=(
                        "b991bedc92cae1b638867cad5ff3efa88db7e33016db9b899cb86df737a40a01"
                    ),
                    source_version=(
                        "degree-finder-entry-2026; page states academic year 2026-27"
                    ),
                    captured_at=FIXED_NOW,
                    verified_at=FIXED_NOW,
                    verified_by="actor.domain_reviewer.product_owner",
                    review_due_at=review_due,
                    expires_at=expires,
                    availability_at_verification=EvidenceAvailability.AVAILABLE,
                    created_at=FIXED_NOW,
                ),
                SourceEvidence(
                    id=POLICY_EVIDENCE_ID,
                    program_id=PILOT_PROGRAM_ID,
                    source_type=SourceType.OFFICIAL_POLICY_PAGE,
                    url=(
                        "https://study.ed.ac.uk/postgraduate/applying/entry-requirements/"
                        "english-language"
                    ),
                    official_domain="study.ed.ac.uk",
                    page_title=(
                        "English language entry requirements | Postgraduate study | "
                        "The University of Edinburgh"
                    ),
                    excerpt=(
                        "IELTS Academic / IELTS Academic for UKVI and IELTS Academic Online"
                    ),
                    snapshot_sha256=(
                        "fd35fcf6eff4926c1544a97b07b8c57ed2ff88d6588668b70c8290f02a5d531e"
                    ),
                    source_version="unversioned; page observed 2026-09-01",
                    captured_at=FIXED_NOW,
                    verified_at=FIXED_NOW,
                    verified_by="actor.domain_reviewer.product_owner",
                    review_due_at=review_due,
                    expires_at=expires,
                    availability_at_verification=EvidenceAvailability.AVAILABLE,
                    created_at=FIXED_NOW,
                ),
            ]
        )
        session.add(
            ProgramVersion(
                id=PILOT_VERSION_ID,
                program_id=PILOT_PROGRAM_ID,
                version_no=1,
                base_version_id=None,
                rollback_of_version_id=None,
                status=VersionStatus.PUBLISHED,
                content_schema_version="program_version_content.v1",
                content_sha256="a" * 64,
                created_by="actor.data_preparer.codex",
                submitted_by="actor.data_preparer.codex",
                reviewed_by="actor.domain_reviewer.product_owner",
                review_note="Pilot 领域复核通过。",
                created_at=FIXED_NOW,
                submitted_at=FIXED_NOW,
                reviewed_at=FIXED_NOW,
                published_at=FIXED_NOW,
            )
        )
        session.add(
            ProgramFieldValue(
                id=PILOT_FIELD_ID,
                program_version_id=PILOT_VERSION_ID,
                field_key="requirements.language.ielts",
                value_schema_version="program_requirement_field.v1",
                value_payload=value_payload,
                display_text="2026–27 IELTS Academic：总分至少 7.0，各项至少 6.5。",
                is_critical=True,
                value_sha256="b" * 64,
            )
        )
        session.add_all(
            [
                FieldEvidenceLink(
                    field_value_id=PILOT_FIELD_ID,
                    evidence_id=PILOT_EVIDENCE_ID,
                    support_scope=EvidenceSupportScope.DIRECT,
                    citation_order=1,
                ),
                FieldEvidenceLink(
                    field_value_id=PILOT_FIELD_ID,
                    evidence_id=POLICY_EVIDENCE_ID,
                    support_scope=EvidenceSupportScope.DEFINITION,
                    citation_order=2,
                ),
                ProgramPublication(
                    program_id=PILOT_PROGRAM_ID,
                    current_version_id=PILOT_VERSION_ID,
                    revision=1,
                    updated_at=FIXED_NOW,
                ),
                AuditEvent(
                    id="audit.pilot.edinburgh.publish.v1",
                    program_id=PILOT_PROGRAM_ID,
                    version_id=PILOT_VERSION_ID,
                    event_type=AuditEventType.PUBLISH,
                    actor_ref="actor.domain_reviewer.product_owner",
                    actor_role=ActorRole.DOMAIN_REVIEWER,
                    reason="Pilot 领域复核通过。",
                    request_id="req_phase3_persistence",
                    idempotency_key_hash="c" * 64,
                    event_payload={"version_no": 1, "status": "published"},
                    created_at=FIXED_NOW,
                ),
                IdempotencyRecord(
                    id="idempotency.pilot.publish.v1",
                    key_hash="c" * 64,
                    operation_type="publish_program_version",
                    request_sha256="d" * 64,
                    response_status=200,
                    response_body={"version_id": PILOT_VERSION_ID},
                    created_at=FIXED_NOW,
                ),
            ]
        )

    first_engine.dispose()

    second_engine = create_database_engine(url)
    assert_database_at_head(second_engine)
    second_sessions = create_session_factory(second_engine)

    with second_sessions() as session:
        publication = session.get(ProgramPublication, PILOT_PROGRAM_ID)
        assert publication is not None
        assert publication.current_version_id == PILOT_VERSION_ID
        assert publication.revision == 1

        version = session.get(ProgramVersion, PILOT_VERSION_ID)
        assert version is not None
        assert version.status == VersionStatus.PUBLISHED
        assert version.content_sha256 == "a" * 64

        field_value = session.get(ProgramFieldValue, PILOT_FIELD_ID)
        assert field_value is not None
        assert field_value.value_payload == value_payload
        assert field_value.value_sha256 == "b" * 64

        links = session.scalars(
            select(FieldEvidenceLink)
            .where(FieldEvidenceLink.field_value_id == PILOT_FIELD_ID)
            .order_by(FieldEvidenceLink.citation_order)
        ).all()
        assert [(link.evidence_id, link.support_scope) for link in links] == [
            (PILOT_EVIDENCE_ID, EvidenceSupportScope.DIRECT),
            (POLICY_EVIDENCE_ID, EvidenceSupportScope.DEFINITION),
        ]

        evidence = session.get(SourceEvidence, PILOT_EVIDENCE_ID)
        assert evidence is not None
        assert evidence.snapshot_sha256 == (
            "b991bedc92cae1b638867cad5ff3efa88db7e33016db9b899cb86df737a40a01"
        )
        assert evidence.verified_by == "actor.domain_reviewer.product_owner"

        audit_events = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.program_id == PILOT_PROGRAM_ID)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        ).all()
        assert [(event.event_type, event.version_id) for event in audit_events] == [
            (AuditEventType.PUBLISH, PILOT_VERSION_ID)
        ]

        idempotency = session.get(IdempotencyRecord, "idempotency.pilot.publish.v1")
        assert idempotency is not None
        assert idempotency.response_body == {"version_id": PILOT_VERSION_ID}

    second_engine.dispose()


def test_sqlite_rejects_orphan_version_after_migration(tmp_path) -> None:
    url = database_url(tmp_path)
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)

    with sessions() as session:
        session.add(
            ProgramVersion(
                id="version.orphan",
                program_id="program.missing",
                version_no=1,
                status=VersionStatus.CANDIDATE,
                content_schema_version="program_version_content.v1",
                content_sha256="e" * 64,
                created_by="actor.data_preparer.codex",
                created_at=FIXED_NOW,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    engine.dispose()
