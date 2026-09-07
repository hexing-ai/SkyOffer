from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import backend.tests.test_phase3_candidates as candidate_support
import backend.tests.test_phase3_version_workflow as workflow_support
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    AuditEvent,
    IdempotencyRecord,
    Program,
    ProgramFieldValue,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    SourceEvidence,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.repositories.candidates import CandidateRepository
from backend.app.repositories.evidence import SourceEvidenceRepository
from backend.app.repositories.idempotency import (
    IdempotencyConflictError,
    IdempotencyExecutor,
    IdempotencyKeyInvalidError,
    IdempotencyRecordImmutableError,
)
from backend.app.schemas.candidates import (
    CandidateCreate,
    CandidateRecord,
    RollbackCandidateCreate,
)
from backend.app.schemas.evidence import SourceEvidenceCreate, SourceEvidenceRecord
from backend.app.schemas.profile_analysis import StrictModel
from backend.app.schemas.version_workflow import VersionTransitionRecord
from backend.app.services.version_workflow import VersionWorkflowService


PROGRAM_ID = candidate_support.PROGRAM_ID
E1 = candidate_support.E1
E2 = candidate_support.E2
E3 = candidate_support.E3
FIXED_NOW = candidate_support.FIXED_NOW
SequenceIds = candidate_support.SequenceIds


class ProbeRecord(StrictModel):
    result: str


@pytest.fixture
def idempotency_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'idempotency.sqlite3'}"
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
    yield url, engine, sessions
    engine.dispose()


def _evidence_payload(evidence_id: str, snapshot_hash: str) -> SourceEvidenceCreate:
    record = candidate_support._evidence(
        evidence_id, snapshot_sha256=snapshot_hash
    )
    return SourceEvidenceCreate.model_validate(
        {
            "id": record.id,
            "program_id": record.program_id,
            "source_type": record.source_type,
            "url": record.url,
            "official_domain": record.official_domain,
            "page_title": record.page_title,
            "excerpt": record.excerpt,
            "snapshot_sha256": record.snapshot_sha256,
            "source_version": record.source_version,
            "captured_at": record.captured_at,
            "verified_at": record.verified_at,
            "verified_by": record.verified_by,
            "review_due_at": record.review_due_at,
            "expires_at": record.expires_at,
            "availability_at_verification": record.availability_at_verification,
        }
    )


def _executor(session, ids, *, now=FIXED_NOW) -> IdempotencyExecutor:
    return IdempotencyExecutor(session, clock=lambda: now, id_factory=ids)


def _execute(
    session,
    ids,
    *,
    key,
    operation,
    request,
    response_model,
    handler,
    now=FIXED_NOW,
):
    return _executor(session, ids, now=now).execute(
        key=key,
        operation_type=operation,
        request_payload=request,
        response_model=response_model,
        handler=handler,
    )


def _create_evidence_idempotently(session, ids, payload, key):
    return _execute(
        session,
        ids,
        key=key,
        operation="source_evidence.create",
        request=payload,
        response_model=SourceEvidenceRecord,
        handler=lambda: SourceEvidenceRepository(
            session, clock=lambda: FIXED_NOW
        ).create(payload),
    )


def test_all_phase3_writes_replay_without_duplicate_business_or_audit_rows(
    idempotency_database,
) -> None:
    _, _, sessions = idempotency_database
    ids = SequenceIds("all-writes")
    keys = {
        "e1": "phase3-evidence-e1-key-0001",
        "e2": "phase3-evidence-e2-key-0002",
        "e3": "phase3-evidence-e3-key-0003",
        "v1_create": "phase3-v1-create-key-0004",
        "v1_submit": "phase3-v1-submit-key-0005",
        "v1_publish": "phase3-v1-publish-key-0006",
        "v2_create": "phase3-v2-create-key-0007",
        "v2_submit": "phase3-v2-submit-key-0008",
        "v2_publish": "phase3-v2-publish-key-0009",
        "rollback": "phase3-rollback-key-0010",
    }

    evidence_payloads = [
        (_evidence_payload(E1, "1" * 64), keys["e1"]),
        (_evidence_payload(E2, "2" * 64), keys["e2"]),
        (_evidence_payload(E3, "3" * 64), keys["e3"]),
    ]
    with sessions.begin() as session:
        first_e1 = _create_evidence_idempotently(
            session, ids, evidence_payloads[0][0], evidence_payloads[0][1]
        )
        replayed_e1 = _create_evidence_idempotently(
            session, ids, evidence_payloads[0][0], evidence_payloads[0][1]
        )
        for payload, key in evidence_payloads[1:]:
            _create_evidence_idempotently(session, ids, payload, key)
    assert replayed_e1 == first_e1

    v1_payload = candidate_support._candidate_payload()
    with sessions.begin() as session:
        create_v1 = lambda: CandidateRepository(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).create(PROGRAM_ID, v1_payload)
        v1 = _execute(
            session,
            ids,
            key=keys["v1_create"],
            operation="candidate.create",
            request={"program_id": PROGRAM_ID, "payload": v1_payload},
            response_model=CandidateRecord,
            handler=create_v1,
        )
        replayed_v1 = _execute(
            session,
            ids,
            key=keys["v1_create"],
            operation="candidate.create",
            request={"payload": v1_payload, "program_id": PROGRAM_ID},
            response_model=CandidateRecord,
            handler=create_v1,
        )
    assert replayed_v1 == v1

    submit_v1 = workflow_support._submit_command()
    with sessions.begin() as session:
        submit_handler = lambda: VersionWorkflowService(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).submit(v1.id, submit_v1)
        pending_v1 = _execute(
            session,
            ids,
            key=keys["v1_submit"],
            operation="version.submit",
            request={"version_id": v1.id, "command": submit_v1},
            response_model=VersionTransitionRecord,
            handler=submit_handler,
        )
        assert _execute(
            session,
            ids,
            key=keys["v1_submit"],
            operation="version.submit",
            request={"command": submit_v1, "version_id": v1.id},
            response_model=VersionTransitionRecord,
            handler=submit_handler,
        ) == pending_v1

    publish_v1 = workflow_support._publish_command(None)
    with sessions.begin() as session:
        publish_handler = lambda: VersionWorkflowService(
            session, clock=lambda: FIXED_NOW, id_factory=ids
        ).publish(v1.id, publish_v1)
        published_v1 = _execute(
            session,
            ids,
            key=keys["v1_publish"],
            operation="version.publish",
            request={"version_id": v1.id, "command": publish_v1},
            response_model=VersionTransitionRecord,
            handler=publish_handler,
        )
        assert _execute(
            session,
            ids,
            key=keys["v1_publish"],
            operation="version.publish",
            request={"version_id": v1.id, "command": publish_v1},
            response_model=VersionTransitionRecord,
            handler=publish_handler,
        ) == published_v1

    v2_payload = candidate_support._candidate_payload(
        base_version_id=v1.id,
        academic_year="2027-28",
        manual_review=True,
        direct_evidence=E3,
        request_id="request.candidate.v2",
    )
    with sessions.begin() as session:
        v2 = _execute(
            session,
            ids,
            key=keys["v2_create"],
            operation="candidate.create",
            request={"program_id": PROGRAM_ID, "payload": v2_payload},
            response_model=CandidateRecord,
            handler=lambda: CandidateRepository(
                session,
                clock=lambda: FIXED_NOW + timedelta(days=1),
                id_factory=ids,
            ).create(PROGRAM_ID, v2_payload),
            now=FIXED_NOW + timedelta(days=1),
        )
    submit_v2 = workflow_support._submit_command(request_id="request.submit.v2")
    with sessions.begin() as session:
        _execute(
            session,
            ids,
            key=keys["v2_submit"],
            operation="version.submit",
            request={"version_id": v2.id, "command": submit_v2},
            response_model=VersionTransitionRecord,
            handler=lambda: VersionWorkflowService(
                session,
                clock=lambda: FIXED_NOW + timedelta(days=1),
                id_factory=ids,
            ).submit(v2.id, submit_v2),
            now=FIXED_NOW + timedelta(days=1),
        )
    publish_v2 = workflow_support._publish_command(
        v1.id, request_id="request.publish.v2"
    )
    with sessions.begin() as session:
        _execute(
            session,
            ids,
            key=keys["v2_publish"],
            operation="version.publish",
            request={"version_id": v2.id, "command": publish_v2},
            response_model=VersionTransitionRecord,
            handler=lambda: VersionWorkflowService(
                session,
                clock=lambda: FIXED_NOW + timedelta(days=1),
                id_factory=ids,
            ).publish(v2.id, publish_v2),
            now=FIXED_NOW + timedelta(days=1),
        )

    rollback_payload = RollbackCandidateCreate(
        expected_current_version_id=v2.id,
        created_by="actor.data_preparer.codex",
        creation_note="Restore v1 through the reviewed rollback workflow.",
        request_id="request.rollback.create",
    )
    with sessions.begin() as session:
        rollback_handler = lambda: CandidateRepository(
            session,
            clock=lambda: FIXED_NOW + timedelta(days=2),
            id_factory=ids,
        ).create_rollback(PROGRAM_ID, v1.id, rollback_payload)
        rollback = _execute(
            session,
            ids,
            key=keys["rollback"],
            operation="rollback_candidate.create",
            request={
                "program_id": PROGRAM_ID,
                "target_version_id": v1.id,
                "payload": rollback_payload,
            },
            response_model=CandidateRecord,
            handler=rollback_handler,
            now=FIXED_NOW + timedelta(days=2),
        )
        replayed_rollback = _execute(
            session,
            ids,
            key=keys["rollback"],
            operation="rollback_candidate.create",
            request={
                "payload": rollback_payload,
                "target_version_id": v1.id,
                "program_id": PROGRAM_ID,
            },
            response_model=CandidateRecord,
            handler=rollback_handler,
            now=FIXED_NOW + timedelta(days=2),
        )
    assert replayed_rollback == rollback

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 3
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 3
        assert session.scalar(select(func.count()).select_from(ProgramFieldValue)) == 3
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 7
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 10
        assert session.get(ProgramPublication, PROGRAM_ID).revision == 2
        audits = session.scalars(select(AuditEvent)).all()
        assert all(event.idempotency_key_hash is not None for event in audits)
        key_hashes = {
            record.key_hash
            for record in session.scalars(select(IdempotencyRecord)).all()
        }
        assert {event.idempotency_key_hash for event in audits}.issubset(key_hashes)

        serialized_records = json.dumps(
            [
                {
                    "id": record.id,
                    "key_hash": record.key_hash,
                    "operation_type": record.operation_type,
                    "request_sha256": record.request_sha256,
                    "response_body": record.response_body,
                }
                for record in session.scalars(select(IdempotencyRecord)).all()
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert all(raw_key not in serialized_records for raw_key in keys.values())
        assert hashlib.sha256(keys["v1_create"].encode()).hexdigest() in key_hashes


def test_same_key_equivalent_canonical_request_replays_first_response(
    idempotency_database,
) -> None:
    _, _, sessions = idempotency_database
    ids = SequenceIds("canonical")
    calls = 0

    def handler() -> ProbeRecord:
        nonlocal calls
        calls += 1
        return ProbeRecord(result="first-response")

    key = "phase3-canonical-probe-key-0001"
    with sessions.begin() as session:
        first = _execute(
            session,
            ids,
            key=key,
            operation="probe.canonical",
            request={
                "score": Decimal("7.00"),
                "nested": {"b": 2, "a": 1},
                "observed_at": datetime.fromisoformat("2026-09-01T08:00:00+08:00"),
            },
            response_model=ProbeRecord,
            handler=handler,
        )
        replayed = _execute(
            session,
            ids,
            key=key,
            operation="probe.canonical",
            request={
                "observed_at": FIXED_NOW,
                "nested": {"a": 1, "b": 2},
                "score": Decimal("7.0"),
            },
            response_model=ProbeRecord,
            handler=handler,
        )

    assert first == replayed == ProbeRecord(result="first-response")
    assert calls == 1


def test_same_key_different_request_or_operation_conflicts_without_handler(
    idempotency_database,
) -> None:
    _, _, sessions = idempotency_database
    ids = SequenceIds("conflict")
    key = "phase3-conflict-probe-key-0001"
    with sessions.begin() as session:
        _execute(
            session,
            ids,
            key=key,
            operation="probe.conflict",
            request={"value": 1},
            response_model=ProbeRecord,
            handler=lambda: ProbeRecord(result="stored"),
        )

    calls = 0

    def forbidden_handler() -> ProbeRecord:
        nonlocal calls
        calls += 1
        return ProbeRecord(result="must-not-run")

    with sessions.begin() as session:
        executor = _executor(session, ids)
        with pytest.raises(IdempotencyConflictError):
            executor.execute(
                key=key,
                operation_type="probe.conflict",
                request_payload={"value": 2},
                response_model=ProbeRecord,
                handler=forbidden_handler,
            )
        with pytest.raises(IdempotencyConflictError):
            executor.execute(
                key=key,
                operation_type="probe.different",
                request_payload={"value": 1},
                response_model=ProbeRecord,
                handler=forbidden_handler,
            )
    assert calls == 0
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


def test_handler_failure_rolls_back_business_audit_and_idempotency_rows(
    idempotency_database,
) -> None:
    _, _, sessions = idempotency_database
    ids = SequenceIds("failure")
    empty_candidate = CandidateCreate(
        base_version_id=None,
        fields=[],
        created_by="actor.data_preparer.codex",
        creation_note="Idempotency failure injection candidate.",
        request_id="request.idempotency.failure",
    )

    with sessions.begin() as session:
        def failing_handler() -> CandidateRecord:
            CandidateRepository(
                session, clock=lambda: FIXED_NOW, id_factory=ids
            ).create(PROGRAM_ID, empty_candidate)
            raise RuntimeError("injected handler failure")

        with pytest.raises(RuntimeError, match="injected handler failure"):
            _execute(
                session,
                ids,
                key="phase3-failing-handler-key-0001",
                operation="candidate.create",
                request={"program_id": PROGRAM_ID, "payload": empty_candidate},
                response_model=CandidateRecord,
                handler=failing_handler,
            )

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_idempotency_record_failure_rolls_back_flushed_business_rows(
    idempotency_database,
) -> None:
    _, _, sessions = idempotency_database
    fixed_record_id = "idempotency.forced-duplicate"
    with sessions.begin() as session:
        IdempotencyExecutor(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=lambda _kind: fixed_record_id,
        ).execute(
            key="phase3-first-record-key-0001",
            operation_type="probe.first_record",
            request_payload={"value": 1},
            response_model=ProbeRecord,
            handler=lambda: ProbeRecord(result="occupy-record-id"),
        )

    business_ids = SequenceIds("record-failure")
    empty_candidate = CandidateCreate(
        base_version_id=None,
        fields=[],
        created_by="actor.data_preparer.codex",
        creation_note="Force idempotency record persistence failure.",
        request_id="request.idempotency.record-failure",
    )
    with sessions.begin() as session:
        executor = IdempotencyExecutor(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=lambda _kind: fixed_record_id,
        )
        with pytest.raises(IntegrityError):
            executor.execute(
                key="phase3-second-record-key-0002",
                operation_type="candidate.create",
                request_payload={
                    "program_id": PROGRAM_ID,
                    "payload": empty_candidate,
                },
                response_model=CandidateRecord,
                handler=lambda: CandidateRepository(
                    session, clock=lambda: FIXED_NOW, id_factory=business_ids
                ).create(PROGRAM_ID, empty_candidate),
            )

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 0
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


def test_idempotency_record_is_immutable_and_replays_after_restart(
    idempotency_database,
) -> None:
    url, first_engine, first_sessions = idempotency_database
    ids = SequenceIds("restart")
    key = "phase3-restart-probe-key-0001"
    with first_sessions.begin() as session:
        created = _execute(
            session,
            ids,
            key=key,
            operation="probe.restart",
            request={"value": "stable"},
            response_model=ProbeRecord,
            handler=lambda: ProbeRecord(result="persisted-response"),
        )

    first_engine.dispose()
    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    calls = 0

    def forbidden_handler() -> ProbeRecord:
        nonlocal calls
        calls += 1
        return ProbeRecord(result="wrong")

    with second_sessions.begin() as session:
        replayed = _execute(
            session,
            ids,
            key=key,
            operation="probe.restart",
            request={"value": "stable"},
            response_model=ProbeRecord,
            handler=forbidden_handler,
        )
    assert replayed == created
    assert calls == 0

    with second_sessions() as session:
        record = session.scalar(select(IdempotencyRecord))
        record.response_status = 201
        with pytest.raises(IdempotencyRecordImmutableError, match="不可修改"):
            session.commit()
        session.rollback()
        record = session.scalar(select(IdempotencyRecord))
        session.delete(record)
        with pytest.raises(IdempotencyRecordImmutableError, match="不可删除"):
            session.commit()
        session.rollback()
    second_engine.dispose()


@pytest.mark.parametrize(
    "invalid_key",
    ["short", " phase3-valid-length-key", "phase3-control-key\n0001"],
)
def test_invalid_idempotency_key_is_rejected(
    idempotency_database, invalid_key
) -> None:
    _, _, sessions = idempotency_database
    with sessions.begin() as session:
        with pytest.raises(IdempotencyKeyInvalidError):
            _execute(
                session,
                SequenceIds("invalid-key"),
                key=invalid_key,
                operation="probe.invalid_key",
                request={"value": 1},
                response_model=ProbeRecord,
                handler=lambda: ProbeRecord(result="must-not-run"),
            )
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0
