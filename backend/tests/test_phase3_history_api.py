from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

import backend.tests.test_phase3_candidates as candidate_support
import backend.tests.test_phase3_internal_api as api_support
import backend.tests.test_phase3_published_api as published_support
from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import AuditEvent, IdempotencyRecord, Program, ProgramRegion, ProgramVersion
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.app.repositories.version_history import AuditEventImmutableError


PROGRAM_ID = candidate_support.PROGRAM_ID
E1 = candidate_support.E1
E2 = candidate_support.E2
E3 = candidate_support.E3
FIXED_NOW = candidate_support.FIXED_NOW
SequenceIds = candidate_support.SequenceIds
INTERNAL = api_support.INTERNAL


@pytest.fixture
def history_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'history-api.sqlite3'}"
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


def _client(sessions, ids) -> TestClient:
    return TestClient(
        create_app(
            Settings(_env_file=None, model_api_key=None),
            phase3_session_factory=sessions,
            phase3_clock=lambda: FIXED_NOW,
            phase3_id_factory=ids,
        ),
        raise_server_exceptions=False,
    )


def _create_published_timeline(client: TestClient):
    v1 = published_support._create_and_publish_v1(client)
    v2 = published_support._create_candidate(
        client,
        "history-v2-create-key-0007",
        base_version_id=v1["id"],
        academic_year="2027-28",
        manual_review=True,
        direct_evidence=E3,
        request_id="request.history.v2",
    )
    published_support._submit(client, v2["id"], "history-v2-submit-key-0008")
    published_support._publish(
        client,
        v2["id"],
        v1["id"],
        "history-v2-publish-key-0009",
    )
    rollback_response = client.post(
        f"{INTERNAL}/programs/{PROGRAM_ID}/rollback-candidates",
        json={
            "target_version_id": v1["id"],
            "expected_current_version_id": v2["id"],
            "created_by": "actor.data_preparer.codex",
            "creation_note": "Restore v1 through the audited rollback workflow.",
        },
        headers=api_support._header("history-v3-rollback-key-0010"),
    )
    assert rollback_response.status_code == 201
    v3 = rollback_response.json()
    published_support._submit(client, v3["id"], "history-v3-submit-key-0011")
    published_support._publish(
        client,
        v3["id"],
        v2["id"],
        "history-v3-publish-key-0012",
    )
    return v1, v2, v3


def test_internal_history_replays_versions_diffs_and_audit_timeline(
    history_database,
) -> None:
    _, _, sessions = history_database
    ids = SequenceIds("history")
    with _client(sessions, ids) as client:
        v1, v2, v3 = _create_published_timeline(client)
        with sessions() as session:
            audit_count_before = session.scalar(
                select(func.count()).select_from(AuditEvent)
            )
            idempotency_count_before = session.scalar(
                select(func.count()).select_from(IdempotencyRecord)
            )

        versions_response = client.get(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions"
        )
        details = {
            version_id: client.get(
                f"{INTERNAL}/program-versions/{version_id}"
            ).json()
            for version_id in (v1["id"], v2["id"], v3["id"])
        }
        diffs = {
            version_id: client.get(
                f"{INTERNAL}/program-versions/{version_id}/diff"
            ).json()
            for version_id in (v1["id"], v2["id"], v3["id"])
        }
        audit_response = client.get(
            f"{INTERNAL}/programs/{PROGRAM_ID}/audit-events"
        )

    assert versions_response.status_code == 200
    versions = versions_response.json()["versions"]
    assert [version["id"] for version in versions] == [v1["id"], v2["id"], v3["id"]]
    assert [version["version_no"] for version in versions] == [1, 2, 3]
    assert [version["status"] for version in versions] == [
        "superseded",
        "superseded",
        "published",
    ]
    assert versions[2]["base_version_id"] == v2["id"]
    assert versions[2]["rollback_of_version_id"] == v1["id"]
    assert versions[2]["content_sha256"] == versions[0]["content_sha256"]

    assert details[v1["id"]]["fields"][0]["value_payload"]["applicable_academic_year"] == "2026-27"
    assert details[v2["id"]]["fields"][0]["value_payload"]["applicable_academic_year"] == "2027-28"
    assert details[v3["id"]]["fields"][0]["value_payload"] == details[v1["id"]]["fields"][0]["value_payload"]
    assert details[v3["id"]]["submitted_by"] == "actor.data_preparer.codex"
    assert details[v3["id"]]["reviewed_by"] == "actor.domain_reviewer.product_owner"

    v1_diff = diffs[v1["id"]]["diff"][0]
    v2_diff = diffs[v2["id"]]["diff"][0]
    v3_diff = diffs[v3["id"]]["diff"][0]
    assert v1_diff["change_type"] == "added"
    assert v1_diff["evidence_added"] == [E1, E2]
    assert v2_diff["change_type"] == "changed"
    assert v2_diff["evidence_removed"] == [E1]
    assert v2_diff["evidence_added"] == [E3]
    assert v3_diff["change_type"] == "changed"
    assert v3_diff["evidence_removed"] == [E3]
    assert v3_diff["evidence_added"] == [E1]

    assert audit_response.status_code == 200
    events = audit_response.json()["events"]
    assert [event["event_type"] for event in events] == [
        "create",
        "submit",
        "publish",
        "create",
        "submit",
        "publish",
        "rollback_candidate_created",
        "submit",
        "publish",
    ]
    assert all(event["idempotency_key_hash"] is not None for event in events)
    assert events[6]["event_payload"]["rollback_of_version_id"] == v1["id"]
    assert events[6]["event_payload"]["base_version_id"] == v2["id"]
    assert all(event["request_id"].startswith("req_") for event in events)

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == audit_count_before
        assert session.scalar(
            select(func.count()).select_from(IdempotencyRecord)
        ) == idempotency_count_before


def test_history_endpoints_return_stable_not_found_errors(history_database) -> None:
    _, _, sessions = history_database
    with _client(sessions, SequenceIds("history-errors")) as client:
        missing_program_versions = client.get(
            f"{INTERNAL}/programs/program.missing/versions"
        )
        missing_program_audit = client.get(
            f"{INTERNAL}/programs/program.missing/audit-events"
        )
        missing_version = client.get(
            f"{INTERNAL}/program-versions/version.missing"
        )
        missing_diff = client.get(
            f"{INTERNAL}/program-versions/version.missing/diff"
        )

    assert missing_program_versions.status_code == 404
    assert missing_program_versions.json()["error"]["code"] == "PROGRAM_NOT_FOUND"
    assert missing_program_audit.json()["error"]["code"] == "PROGRAM_NOT_FOUND"
    assert missing_version.status_code == 404
    assert missing_version.json()["error"]["code"] == "VERSION_NOT_FOUND"
    assert missing_diff.json()["error"]["code"] == "VERSION_NOT_FOUND"
    for response in (
        missing_program_versions,
        missing_program_audit,
        missing_version,
        missing_diff,
    ):
        assert response.json()["error"]["request_id"].startswith("req_")
        assert "sqlite" not in response.text.lower()


def test_history_integrity_error_does_not_return_partial_history(
    history_database,
) -> None:
    _, _, sessions = history_database
    ids = SequenceIds("history-integrity")
    with _client(sessions, ids) as client:
        v1, _, _ = _create_published_timeline(client)
        with sessions.begin() as session:
            session.execute(
                update(ProgramVersion)
                .where(ProgramVersion.id == v1["id"])
                .values(content_sha256="f" * 64)
            )
        versions = client.get(f"{INTERNAL}/programs/{PROGRAM_ID}/versions")
        detail = client.get(f"{INTERNAL}/program-versions/{v1['id']}")
        diff = client.get(f"{INTERNAL}/program-versions/{v1['id']}/diff")

    for response in (versions, detail, diff):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "VERSION_HISTORY_INTEGRITY_ERROR"
        assert v1["id"] not in response.text
        assert "program_versions" not in response.text


def test_audit_events_cannot_be_updated_or_deleted(history_database) -> None:
    _, _, sessions = history_database
    with _client(sessions, SequenceIds("audit-immutable")) as client:
        _create_published_timeline(client)

    with sessions() as session:
        event = session.scalar(select(AuditEvent).order_by(AuditEvent.id))
        original_reason = event.reason
        event.reason = "attempted audit rewrite"
        with pytest.raises(AuditEventImmutableError, match="不可修改"):
            session.commit()
        session.rollback()

        event = session.scalar(select(AuditEvent).order_by(AuditEvent.id))
        session.delete(event)
        with pytest.raises(AuditEventImmutableError, match="不可删除"):
            session.commit()
        session.rollback()

    with sessions() as session:
        event = session.scalar(select(AuditEvent).order_by(AuditEvent.id))
        assert event.reason == original_reason
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 9


def test_history_and_audit_survive_app_and_engine_restart(history_database) -> None:
    url, first_engine, first_sessions = history_database
    with _client(first_sessions, SequenceIds("history-restart-first")) as client:
        _, _, v3 = _create_published_timeline(client)
        first_versions = client.get(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions"
        ).json()
        first_detail = client.get(
            f"{INTERNAL}/program-versions/{v3['id']}"
        ).json()
        first_audit = client.get(
            f"{INTERNAL}/programs/{PROGRAM_ID}/audit-events"
        ).json()
    first_engine.dispose()

    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    with _client(second_sessions, SequenceIds("history-restart-second")) as client:
        restored_versions = client.get(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions"
        ).json()
        restored_detail = client.get(
            f"{INTERNAL}/program-versions/{v3['id']}"
        ).json()
        restored_audit = client.get(
            f"{INTERNAL}/programs/{PROGRAM_ID}/audit-events"
        ).json()

    assert restored_versions == first_versions
    assert restored_detail == first_detail
    assert restored_audit == first_audit
    second_engine.dispose()
