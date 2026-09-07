from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

import backend.tests.test_phase3_candidates as candidate_support
import backend.tests.test_phase3_version_workflow as workflow_support
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    AuditEvent,
    AuditEventType,
    Program,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.repositories.candidates import (
    CandidateRepository,
    CandidateRollbackPublicationRequiredError,
    CandidateRollbackStalePublicationError,
    CandidateRollbackTargetNotFoundError,
    CandidateRollbackTargetProgramMismatchError,
    CandidateRollbackTargetStatusError,
)
from backend.app.schemas.candidates import RollbackCandidateCreate
from backend.app.services.version_workflow import (
    VersionTransitionInvalidError,
    VersionWorkflowService,
)


PROGRAM_ID = candidate_support.PROGRAM_ID
E1 = candidate_support.E1
E2 = candidate_support.E2
E3 = candidate_support.E3
FIXED_NOW = candidate_support.FIXED_NOW
SequenceIds = candidate_support.SequenceIds


@pytest.fixture
def rollback_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'rollback.sqlite3'}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        session.add(
            Program(
                id=PROGRAM_ID,
                official_name="Computer Science MSc",
                institution_name="The University of Edinburgh",
                region=ProgramRegion.UNITED_KINGDOM,
                official_program_url="https://study.ed.ac.uk/programmes/pilot",
                registered_official_domain="ed.ac.uk",
                created_at=FIXED_NOW,
            )
        )
        session.add_all(
            [
                candidate_support._evidence(E1, snapshot_sha256="1" * 64),
                candidate_support._evidence(E2, snapshot_sha256="2" * 64),
                candidate_support._evidence(E3, snapshot_sha256="3" * 64),
            ]
        )
    yield url, engine, sessions
    engine.dispose()


def _repository(session, ids, *, now=FIXED_NOW):
    return CandidateRepository(session, clock=lambda: now, id_factory=ids)


def _workflow(session, ids, *, now=FIXED_NOW):
    return VersionWorkflowService(session, clock=lambda: now, id_factory=ids)


def _rollback_command(
    current_version_id: str,
    *,
    request_id: str = "request.rollback.create",
) -> RollbackCandidateCreate:
    return RollbackCandidateCreate(
        expected_current_version_id=current_version_id,
        created_by="actor.data_preparer.codex",
        creation_note="Restore the previously reviewed v1 content through a new candidate.",
        request_id=request_id,
    )


def _create_two_published_versions(sessions, ids):
    with sessions.begin() as session:
        v1 = _repository(session, ids).create(
            PROGRAM_ID, candidate_support._candidate_payload()
        )
    with sessions.begin() as session:
        _workflow(session, ids).submit(v1.id, workflow_support._submit_command())
    with sessions.begin() as session:
        _workflow(session, ids).publish(
            v1.id, workflow_support._publish_command(None)
        )

    with sessions.begin() as session:
        v2 = _repository(session, ids, now=FIXED_NOW + timedelta(days=1)).create(
            PROGRAM_ID,
            candidate_support._candidate_payload(
                base_version_id=v1.id,
                academic_year="2027-28",
                manual_review=True,
                direct_evidence=E3,
                request_id="request.candidate.v2",
            ),
        )
    with sessions.begin() as session:
        _workflow(session, ids, now=FIXED_NOW + timedelta(days=1)).submit(
            v2.id,
            workflow_support._submit_command(request_id="request.submit.v2"),
        )
    with sessions.begin() as session:
        _workflow(session, ids, now=FIXED_NOW + timedelta(days=1)).publish(
            v2.id,
            workflow_support._publish_command(
                v1.id, request_id="request.publish.v2"
            ),
        )
    return v1, v2


def test_rollback_command_is_strict() -> None:
    payload = _rollback_command("version.current").model_dump(mode="python")
    payload["target_version_id"] = "version.client.supplied"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RollbackCandidateCreate.model_validate(payload)


def test_historical_version_is_copied_to_new_candidate_with_identical_content(
    rollback_database,
) -> None:
    _, _, sessions = rollback_database
    ids = SequenceIds("copy")
    v1, v2 = _create_two_published_versions(sessions, ids)

    with sessions.begin() as session:
        rollback = _repository(
            session, ids, now=FIXED_NOW + timedelta(days=2)
        ).create_rollback(PROGRAM_ID, v1.id, _rollback_command(v2.id))

    assert rollback.id not in {v1.id, v2.id}
    assert rollback.version_no == 3
    assert rollback.status == VersionStatus.CANDIDATE
    assert rollback.base_version_id == v2.id
    assert rollback.rollback_of_version_id == v1.id
    assert rollback.content_sha256 == v1.content_sha256
    assert rollback.fields[0].id != v1.fields[0].id
    assert rollback.fields[0].value_sha256 == v1.fields[0].value_sha256
    assert rollback.fields[0].value_payload == v1.fields[0].value_payload
    assert rollback.fields[0].evidence_links == v1.fields[0].evidence_links
    assert rollback.diff[0].change_type == "changed"
    assert rollback.diff[0].evidence_removed == [E3]
    assert rollback.diff[0].evidence_added == [E1]

    with sessions() as session:
        publication = session.get(ProgramPublication, PROGRAM_ID)
        assert publication.current_version_id == v2.id
        assert publication.revision == 2
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.version_id == rollback.id,
                AuditEvent.event_type
                == AuditEventType.ROLLBACK_CANDIDATE_CREATED,
            )
        )
        assert audit is not None
        assert audit.event_payload["rollback_of_version_id"] == v1.id
        assert audit.event_payload["base_version_id"] == v2.id
        assert session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.version_id == rollback.id)
        ) == 1


def test_rollback_candidate_must_repeat_submit_and_publish(
    rollback_database,
) -> None:
    _, _, sessions = rollback_database
    ids = SequenceIds("workflow")
    v1, v2 = _create_two_published_versions(sessions, ids)
    with sessions.begin() as session:
        rollback = _repository(
            session, ids, now=FIXED_NOW + timedelta(days=2)
        ).create_rollback(PROGRAM_ID, v1.id, _rollback_command(v2.id))

    with sessions.begin() as session:
        with pytest.raises(VersionTransitionInvalidError):
            _workflow(session, ids, now=FIXED_NOW + timedelta(days=2)).publish(
                rollback.id,
                workflow_support._publish_command(
                    v2.id, request_id="request.rollback.direct-publish"
                ),
            )
    with sessions() as session:
        assert session.get(ProgramPublication, PROGRAM_ID).current_version_id == v2.id
        assert session.get(ProgramVersion, rollback.id).status == VersionStatus.CANDIDATE

    with sessions.begin() as session:
        _workflow(session, ids, now=FIXED_NOW + timedelta(days=2)).submit(
            rollback.id,
            workflow_support._submit_command(
                request_id="request.rollback.submit"
            ),
        )
    with sessions.begin() as session:
        published = _workflow(
            session, ids, now=FIXED_NOW + timedelta(days=2)
        ).publish(
            rollback.id,
            workflow_support._publish_command(
                v2.id, request_id="request.rollback.publish"
            ),
        )

    assert published.status == VersionStatus.PUBLISHED
    assert published.current_version_id == rollback.id
    assert published.publication_revision == 3
    with sessions() as session:
        persisted_v1 = session.get(ProgramVersion, v1.id)
        persisted_v2 = session.get(ProgramVersion, v2.id)
        persisted_v3 = session.get(ProgramVersion, rollback.id)
        assert persisted_v1.status == VersionStatus.SUPERSEDED
        assert persisted_v2.status == VersionStatus.SUPERSEDED
        assert persisted_v3.status == VersionStatus.PUBLISHED
        assert persisted_v1.content_sha256 == persisted_v3.content_sha256
        assert persisted_v1.created_by == v1.created_by
        assert persisted_v1.created_at == v1.created_at


def test_stale_current_rejects_rollback_without_side_effects(
    rollback_database,
) -> None:
    _, _, sessions = rollback_database
    ids = SequenceIds("stale")
    v1, v2 = _create_two_published_versions(sessions, ids)
    with sessions.begin() as session:
        before_versions = session.scalar(
            select(func.count()).select_from(ProgramVersion)
        )
        before_audits = session.scalar(select(func.count()).select_from(AuditEvent))
        with pytest.raises(CandidateRollbackStalePublicationError):
            _repository(session, ids).create_rollback(
                PROGRAM_ID, v1.id, _rollback_command(v1.id)
            )

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == before_versions
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == before_audits
        assert session.get(ProgramPublication, PROGRAM_ID).current_version_id == v2.id


def test_missing_cross_program_and_invalid_status_targets_are_rejected(
    rollback_database,
) -> None:
    _, _, sessions = rollback_database
    ids = SequenceIds("targets")
    v1, v2 = _create_two_published_versions(sessions, ids)

    with sessions.begin() as session:
        invalid_candidate = _repository(session, ids).create(
            PROGRAM_ID,
            candidate_support._candidate_payload(
                base_version_id=v2.id,
                request_id="request.candidate.invalid-target",
            ),
        )
        session.add(
            Program(
                id="program.pilot.other.rollback",
                official_name="Other Pilot MSc",
                institution_name="Other Pilot University",
                region=ProgramRegion.UNITED_KINGDOM,
                official_program_url="https://example.ac.uk/programmes/pilot",
                registered_official_domain="example.ac.uk",
                created_at=FIXED_NOW,
            )
        )
    with sessions.begin() as session:
        rejected_target = _repository(session, ids).create(
            PROGRAM_ID,
            candidate_support._candidate_payload(
                base_version_id=v2.id,
                request_id="request.candidate.rejected-target",
            ),
        )
    with sessions.begin() as session:
        _workflow(session, ids).submit(
            rejected_target.id,
            workflow_support._submit_command(
                request_id="request.submit.rejected-target"
            ),
        )
    with sessions.begin() as session:
        _workflow(session, ids).reject(
            rejected_target.id,
            workflow_support._reject_command(
                request_id="request.reject.rejected-target"
            ),
        )
        session.add(
            ProgramVersion(
                id="version.pilot.other.superseded",
                program_id="program.pilot.other.rollback",
                version_no=1,
                status=VersionStatus.SUPERSEDED,
                content_schema_version="program_version_content.v1",
                content_sha256="8" * 64,
                created_by="actor.data_preparer.other",
                created_at=FIXED_NOW,
            )
        )

    cases = [
        (
            "version.missing",
            CandidateRollbackTargetNotFoundError,
        ),
        (
            "version.pilot.other.superseded",
            CandidateRollbackTargetProgramMismatchError,
        ),
        (
            invalid_candidate.id,
            CandidateRollbackTargetStatusError,
        ),
        (
            rejected_target.id,
            CandidateRollbackTargetStatusError,
        ),
    ]
    for target_version_id, expected_error in cases:
        with sessions.begin() as session:
            before_versions = session.scalar(
                select(func.count()).select_from(ProgramVersion)
            )
            before_audits = session.scalar(
                select(func.count()).select_from(AuditEvent)
            )
            with pytest.raises(expected_error):
                _repository(session, ids).create_rollback(
                    PROGRAM_ID,
                    target_version_id,
                    _rollback_command(v2.id),
                )
        with sessions() as session:
            assert session.scalar(
                select(func.count()).select_from(ProgramVersion)
            ) == before_versions
            assert session.scalar(
                select(func.count()).select_from(AuditEvent)
            ) == before_audits


def test_project_without_publication_cannot_prepare_rollback(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'no-publication.sqlite3'}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        session.add(
            Program(
                id=PROGRAM_ID,
                official_name="Computer Science MSc",
                institution_name="The University of Edinburgh",
                region=ProgramRegion.UNITED_KINGDOM,
                official_program_url="https://study.ed.ac.uk/programmes/pilot",
                registered_official_domain="ed.ac.uk",
                created_at=FIXED_NOW,
            )
        )
    with sessions.begin() as session:
        with pytest.raises(CandidateRollbackPublicationRequiredError):
            _repository(session, SequenceIds("no-publication")).create_rollback(
                PROGRAM_ID,
                "version.missing",
                _rollback_command("version.expected.current"),
            )
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    engine.dispose()


def test_rollback_candidate_survives_database_restart(rollback_database) -> None:
    url, first_engine, first_sessions = rollback_database
    ids = SequenceIds("restart")
    v1, v2 = _create_two_published_versions(first_sessions, ids)
    with first_sessions.begin() as session:
        created = _repository(
            session, ids, now=FIXED_NOW + timedelta(days=2)
        ).create_rollback(PROGRAM_ID, v1.id, _rollback_command(v2.id))

    first_engine.dispose()
    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    with second_sessions() as session:
        restored = _repository(session, ids).get(created.id)

    assert restored == created
    assert restored is not None
    assert restored.rollback_of_version_id == v1.id
    assert restored.content_sha256 == v1.content_sha256
    second_engine.dispose()
