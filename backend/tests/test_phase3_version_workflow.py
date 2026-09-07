from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

import backend.tests.test_phase3_candidates as candidate_support
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    ActorRole,
    AuditEvent,
    AuditEventType,
    EvidenceAvailability,
    Program,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.repositories.candidates import CandidateRepository
from backend.app.schemas.candidates import CandidateCreate
from backend.app.schemas.version_workflow import (
    PublishVersionCommand,
    ReviewVersionCommand,
    SubmitVersionCommand,
)
from backend.app.services.version_workflow import (
    VersionCriticalFieldRequiredError,
    VersionDirectEvidenceRequiredError,
    VersionEvidenceInvalidError,
    VersionEvidenceNotFreshError,
    VersionSelfReviewForbiddenError,
    VersionStaleBaseError,
    VersionStalePublicationError,
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
def workflow_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'workflow.sqlite3'}"
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
    yield engine, sessions
    engine.dispose()


def _submit_command(
    actor: str = "actor.data_preparer.codex",
    request_id: str = "request.workflow.submit",
) -> SubmitVersionCommand:
    return SubmitVersionCommand(
        submitted_by=actor,
        submission_note="Official evidence and structured field are ready for review.",
        request_id=request_id,
    )


def _publish_command(
    expected_current_version_id: str | None,
    *,
    actor: str = "actor.domain_reviewer.product_owner",
    request_id: str = "request.workflow.publish",
) -> PublishVersionCommand:
    return PublishVersionCommand(
        reviewed_by=actor,
        review_note="Official source, field payload and diff have been reviewed.",
        request_id=request_id,
        expected_current_version_id=expected_current_version_id,
    )


def _reject_command(
    *,
    actor: str = "actor.domain_reviewer.product_owner",
    request_id: str = "request.workflow.reject",
) -> ReviewVersionCommand:
    return ReviewVersionCommand(
        reviewed_by=actor,
        review_note="The candidate needs a new official source before publication.",
        request_id=request_id,
    )


def _create_candidate(session, ids, **payload_overrides):
    return CandidateRepository(
        session, clock=lambda: FIXED_NOW, id_factory=ids
    ).create(
        PROGRAM_ID,
        candidate_support._candidate_payload(**payload_overrides),
    )


def _service(session, ids, *, now=FIXED_NOW, failure_hook=None):
    return VersionWorkflowService(
        session,
        clock=lambda: now,
        id_factory=ids,
        failure_hook=failure_hook,
    )


def _create_submit_publish_v1(sessions, ids):
    with sessions.begin() as session:
        candidate = _create_candidate(session, ids)
    with sessions.begin() as session:
        _service(session, ids).submit(candidate.id, _submit_command())
    with sessions.begin() as session:
        published = _service(session, ids).publish(
            candidate.id, _publish_command(None)
        )
    return candidate, published


def test_workflow_commands_are_strict() -> None:
    payload = _submit_command().model_dump(mode="python")
    payload["role"] = "data_preparer"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SubmitVersionCommand.model_validate(payload)

    with pytest.raises(ValidationError):
        ReviewVersionCommand(
            reviewed_by="actor.domain_reviewer.product_owner",
            review_note=" ",
            request_id="request.workflow.reject",
        )


def test_candidate_submit_publish_creates_pointer_and_audit_timeline(
    workflow_database,
) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("legal")
    with sessions.begin() as session:
        candidate = _create_candidate(session, ids)
    with sessions.begin() as session:
        pending = _service(session, ids).submit(candidate.id, _submit_command())
    with sessions.begin() as session:
        published = _service(session, ids).publish(
            candidate.id, _publish_command(None)
        )

    assert pending.status == VersionStatus.PENDING_REVIEW
    assert pending.submitted_by == "actor.data_preparer.codex"
    assert pending.submitted_at == FIXED_NOW
    assert published.status == VersionStatus.PUBLISHED
    assert published.reviewed_by == "actor.domain_reviewer.product_owner"
    assert published.reviewed_at == FIXED_NOW
    assert published.published_at == FIXED_NOW
    assert published.current_version_id == candidate.id
    assert published.publication_revision == 1

    with sessions() as session:
        events = session.scalars(
            select(AuditEvent).order_by(AuditEvent.id)
        ).all()
        assert [event.event_type for event in events] == [
            AuditEventType.CREATE,
            AuditEventType.SUBMIT,
            AuditEventType.PUBLISH,
        ]
        by_type = {event.event_type: event for event in events}
        assert by_type[AuditEventType.SUBMIT].actor_role == ActorRole.DATA_PREPARER
        assert by_type[AuditEventType.PUBLISH].actor_role == ActorRole.DOMAIN_REVIEWER
        assert by_type[AuditEventType.SUBMIT].reason
        assert by_type[AuditEventType.PUBLISH].reason


def test_reject_preserves_current_publication(workflow_database) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("reject")
    v1, _ = _create_submit_publish_v1(sessions, ids)
    with sessions.begin() as session:
        v2 = _create_candidate(
            session,
            ids,
            base_version_id=v1.id,
            academic_year="2027-28",
            manual_review=True,
            direct_evidence=E3,
            request_id="request.candidate.v2",
        )
    with sessions.begin() as session:
        _service(session, ids).submit(
            v2.id,
            _submit_command(request_id="request.workflow.submit.v2"),
        )
    with sessions.begin() as session:
        rejected = _service(session, ids).reject(v2.id, _reject_command())

    assert rejected.status == VersionStatus.REJECTED
    assert rejected.current_version_id == v1.id
    assert rejected.publication_revision == 1
    assert rejected.published_at is None
    with sessions() as session:
        assert session.get(ProgramVersion, v1.id).status == VersionStatus.PUBLISHED
        assert session.get(ProgramVersion, v2.id).status == VersionStatus.REJECTED
        assert session.get(ProgramPublication, PROGRAM_ID).current_version_id == v1.id


def test_second_publish_supersedes_old_current_and_increments_revision(
    workflow_database,
) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("supersede")
    v1, _ = _create_submit_publish_v1(sessions, ids)
    with sessions.begin() as session:
        v2 = _create_candidate(
            session,
            ids,
            base_version_id=v1.id,
            academic_year="2027-28",
            manual_review=True,
            direct_evidence=E3,
            request_id="request.candidate.v2",
        )
    with sessions.begin() as session:
        _service(session, ids).submit(
            v2.id, _submit_command(request_id="request.workflow.submit.v2")
        )
    with sessions.begin() as session:
        published = _service(session, ids).publish(
            v2.id,
            _publish_command(v1.id, request_id="request.workflow.publish.v2"),
        )

    assert published.current_version_id == v2.id
    assert published.publication_revision == 2
    with sessions() as session:
        assert session.get(ProgramVersion, v1.id).status == VersionStatus.SUPERSEDED
        assert session.get(ProgramVersion, v2.id).status == VersionStatus.PUBLISHED


def test_illegal_and_repeated_transitions_have_no_side_effects(
    workflow_database,
) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("invalid")
    with sessions.begin() as session:
        candidate = _create_candidate(session, ids)

    with sessions.begin() as session:
        service = _service(session, ids)
        with pytest.raises(VersionTransitionInvalidError):
            service.publish(candidate.id, _publish_command(None))

    with sessions.begin() as session:
        _service(session, ids).submit(candidate.id, _submit_command())
    with sessions.begin() as session:
        service = _service(session, ids)
        with pytest.raises(VersionTransitionInvalidError):
            service.submit(candidate.id, _submit_command())

    with sessions.begin() as session:
        _service(session, ids).publish(candidate.id, _publish_command(None))
    with sessions.begin() as session:
        service = _service(session, ids)
        with pytest.raises(VersionTransitionInvalidError):
            service.publish(candidate.id, _publish_command(candidate.id))
        with pytest.raises(VersionTransitionInvalidError):
            service.reject(candidate.id, _reject_command())
        with pytest.raises(VersionTransitionInvalidError):
            service.submit(candidate.id, _submit_command())

    with sessions() as session:
        version = session.get(ProgramVersion, candidate.id)
        assert version.status == VersionStatus.PUBLISHED
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 3


def test_submitter_cannot_publish_or_reject_own_version(workflow_database) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("four-eyes")
    submitter = "actor.data_preparer.same_person"
    with sessions.begin() as session:
        candidate = _create_candidate(session, ids)
    with sessions.begin() as session:
        _service(session, ids).submit(
            candidate.id, _submit_command(actor=submitter)
        )

    with sessions.begin() as session:
        service = _service(session, ids)
        with pytest.raises(VersionSelfReviewForbiddenError):
            service.publish(
                candidate.id,
                _publish_command(None, actor=submitter),
            )
        with pytest.raises(VersionSelfReviewForbiddenError):
            service.reject(candidate.id, _reject_command(actor=submitter))

    with sessions() as session:
        version = session.get(ProgramVersion, candidate.id)
        assert version.status == VersionStatus.PENDING_REVIEW
        assert version.reviewed_by is None
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 2


@pytest.mark.parametrize(
    "publish_time",
    [
        FIXED_NOW + timedelta(days=30),
        FIXED_NOW + timedelta(days=38),
    ],
)
def test_review_due_or_expired_evidence_cannot_publish(
    workflow_database, publish_time
) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("stale-evidence")
    with sessions.begin() as session:
        candidate = _create_candidate(session, ids)
    with sessions.begin() as session:
        _service(session, ids).submit(candidate.id, _submit_command())
    with sessions.begin() as session:
        with pytest.raises(VersionEvidenceNotFreshError):
            _service(session, ids, now=publish_time).publish(
                candidate.id, _publish_command(None)
            )

    with sessions() as session:
        assert session.get(ProgramVersion, candidate.id).status == VersionStatus.PENDING_REVIEW
        assert session.get(ProgramPublication, PROGRAM_ID) is None


@pytest.mark.parametrize("invalid_kind", ["source_unavailable", "unverified"])
def test_unavailable_or_unverified_evidence_cannot_publish(
    workflow_database, invalid_kind
) -> None:
    _, sessions = workflow_database
    ids = SequenceIds(f"invalid-evidence-{invalid_kind}")
    evidence_id = f"evidence.pilot.workflow.{invalid_kind}"
    evidence = candidate_support._evidence(evidence_id, snapshot_sha256="9" * 64)
    if invalid_kind == "source_unavailable":
        evidence.availability_at_verification = EvidenceAvailability.SOURCE_UNAVAILABLE
        expected_error = VersionEvidenceNotFreshError
    else:
        evidence.verified_by = ""
        expected_error = VersionEvidenceInvalidError
    with sessions.begin() as session:
        session.add(evidence)
    with sessions.begin() as session:
        candidate = _create_candidate(
            session, ids, direct_evidence=evidence_id
        )
    with sessions.begin() as session:
        _service(session, ids).submit(candidate.id, _submit_command())
    with sessions.begin() as session:
        with pytest.raises(expected_error):
            _service(session, ids).publish(candidate.id, _publish_command(None))

    with sessions() as session:
        assert session.get(ProgramVersion, candidate.id).status == VersionStatus.PENDING_REVIEW
        assert session.get(ProgramPublication, PROGRAM_ID) is None


def test_direct_evidence_is_required_for_publish(workflow_database) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("direct")
    with sessions.begin() as session:
        candidate = _create_candidate(
            session, ids, direct_scope="definition"
        )
    with sessions.begin() as session:
        _service(session, ids).submit(candidate.id, _submit_command())
    with sessions.begin() as session:
        with pytest.raises(VersionDirectEvidenceRequiredError):
            _service(session, ids).publish(candidate.id, _publish_command(None))

    with sessions() as session:
        assert session.get(ProgramVersion, candidate.id).status == VersionStatus.PENDING_REVIEW


def test_empty_snapshot_cannot_be_submitted(workflow_database) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("empty")
    payload = CandidateCreate(
        base_version_id=None,
        fields=[],
        created_by="actor.data_preparer.codex",
        creation_note="Empty snapshot boundary test.",
        request_id="request.candidate.empty",
    )
    with sessions.begin() as session:
        candidate = CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).create(PROGRAM_ID, payload)
    with sessions.begin() as session:
        with pytest.raises(VersionCriticalFieldRequiredError):
            _service(session, ids).submit(candidate.id, _submit_command())

    with sessions() as session:
        assert session.get(ProgramVersion, candidate.id).status == VersionStatus.CANDIDATE
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_stale_publication_and_stale_base_cannot_overwrite_current(
    workflow_database,
) -> None:
    _, sessions = workflow_database
    ids = SequenceIds("stale")
    v1, _ = _create_submit_publish_v1(sessions, ids)
    with sessions.begin() as session:
        candidate_a = _create_candidate(
            session, ids, base_version_id=v1.id, request_id="request.candidate.a"
        )
        candidate_b = _create_candidate(
            session, ids, base_version_id=v1.id, request_id="request.candidate.b"
        )
    with sessions.begin() as session:
        service = _service(session, ids)
        service.submit(candidate_a.id, _submit_command(request_id="request.submit.a"))
        service.submit(candidate_b.id, _submit_command(request_id="request.submit.b"))
    with sessions.begin() as session:
        _service(session, ids).publish(
            candidate_a.id,
            _publish_command(v1.id, request_id="request.publish.a"),
        )

    with sessions.begin() as session:
        service = _service(session, ids)
        with pytest.raises(VersionStalePublicationError):
            service.publish(
                candidate_b.id,
                _publish_command(v1.id, request_id="request.publish.b.stale-pointer"),
            )
        with pytest.raises(VersionStaleBaseError):
            service.publish(
                candidate_b.id,
                _publish_command(
                    candidate_a.id,
                    request_id="request.publish.b.stale-base",
                ),
            )

    with sessions() as session:
        publication = session.get(ProgramPublication, PROGRAM_ID)
        assert publication.current_version_id == candidate_a.id
        assert publication.revision == 2
        assert session.get(ProgramVersion, candidate_b.id).status == VersionStatus.PENDING_REVIEW
        publish_events_for_b = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.version_id == candidate_b.id,
                AuditEvent.event_type == AuditEventType.PUBLISH,
            )
        )
        assert publish_events_for_b == 0


@pytest.mark.parametrize(
    "failure_step",
    [
        "after_old_version_superseded",
        "after_new_version_published",
        "after_publication_pointer_updated",
        "after_publish_audit_added",
    ],
)
def test_publish_failure_injection_rolls_back_every_side_effect(
    workflow_database, failure_step
) -> None:
    _, sessions = workflow_database
    ids = SequenceIds(f"atomic-{failure_step}")
    v1, _ = _create_submit_publish_v1(sessions, ids)
    with sessions.begin() as session:
        v2 = _create_candidate(
            session,
            ids,
            base_version_id=v1.id,
            academic_year="2027-28",
            manual_review=True,
            direct_evidence=E3,
            request_id="request.candidate.v2",
        )
    with sessions.begin() as session:
        _service(session, ids).submit(
            v2.id, _submit_command(request_id="request.submit.v2")
        )

    def fail_at(step: str) -> None:
        if step == failure_step:
            raise RuntimeError(f"injected failure: {step}")

    with sessions.begin() as session:
        with pytest.raises(RuntimeError, match="injected failure"):
            _service(session, ids, failure_hook=fail_at).publish(
                v2.id, _publish_command(v1.id)
            )

    with sessions() as session:
        publication = session.get(ProgramPublication, PROGRAM_ID)
        assert publication.current_version_id == v1.id
        assert publication.revision == 1
        assert session.get(ProgramVersion, v1.id).status == VersionStatus.PUBLISHED
        assert session.get(ProgramVersion, v2.id).status == VersionStatus.PENDING_REVIEW
        assert session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.version_id == v2.id,
                AuditEvent.event_type == AuditEventType.PUBLISH,
            )
        ) == 0
