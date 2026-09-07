from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import AuditEvent, IdempotencyRecord, Program, SourceEvidence
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app


INTERNAL = "/api/v1/internal"
FIXED_NOW = datetime(2026, 9, 1, 8, 30, tzinfo=timezone.utc)


class SequenceIds:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        next_value = self.counts.get(kind, 0) + 1
        self.counts[kind] = next_value
        return f"{kind}.{self.namespace}.{next_value}"


class MutableClock:
    def __init__(self, current: datetime = FIXED_NOW) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


@pytest.fixture
def program_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'program-api.sqlite3'}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    yield url, engine, sessions
    engine.dispose()


def _client(sessions, ids, clock) -> TestClient:
    return TestClient(
        create_app(
            Settings(_env_file=None, model_api_key=None),
            phase3_session_factory=sessions,
            phase3_clock=clock,
            phase3_id_factory=ids,
        ),
        raise_server_exceptions=False,
    )


def _header(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


def _program_payload() -> dict:
    return {
        "official_name": "MSc Computer Science",
        "institution_name": "The University of Edinburgh",
        "region": "united_kingdom",
        "official_program_url": (
            " HTTPS://STUDY.ED.AC.UK/programmes/msc-computer-science?b=2&a=1#entry "
        ),
        "registered_official_domain": " ED.AC.UK. ",
        "created_by": "actor.data_preparer.domain_owner",
        "creation_note": "登记 Pilot 项目并保留来源边界。",
    }


def _evidence_payload(
    program_id: str,
    evidence_id: str,
    *,
    captured_at: str,
    review_due_at: str,
    expires_at: str,
    hash_character: str,
) -> dict:
    return {
        "id": evidence_id,
        "program_id": program_id,
        "source_type": "official_program_page",
        "url": f"https://study.ed.ac.uk/programmes/{evidence_id}",
        "official_domain": "study.ed.ac.uk",
        "page_title": f"Official source for {evidence_id}",
        "excerpt": f"Verified excerpt for {evidence_id}",
        "snapshot_sha256": hash_character * 64,
        "source_version": "official page observed 2026-09-01",
        "captured_at": captured_at,
        "verified_at": captured_at,
        "verified_by": "actor.domain_reviewer.product_owner",
        "review_due_at": review_due_at,
        "expires_at": expires_at,
        "availability_at_verification": "available",
    }


def _create_program(client: TestClient, *, key: str = "program-create-key-0001"):
    return client.post(
        f"{INTERNAL}/programs",
        json=_program_payload(),
        headers=_header(key),
    )


def test_program_create_is_normalized_idempotent_and_audited(program_database) -> None:
    _, _, sessions = program_database
    key = "program-create-idempotent-key-0001"
    with _client(sessions, SequenceIds("program-create"), MutableClock()) as client:
        first = _create_program(client, key=key)
        replay = _create_program(client, key=key)
        assert first.status_code == 201
        assert replay.status_code == 201
        assert replay.json() == first.json()

        record = first.json()
        assert record["id"] == "program.program-create.1"
        assert record["official_program_url"] == (
            "https://study.ed.ac.uk/programmes/msc-computer-science?a=1&b=2"
        )
        assert record["registered_official_domain"] == "ed.ac.uk"
        assert record["created_by"] == "actor.data_preparer.domain_owner"
        timeline = client.get(
            f"{INTERNAL}/programs/{record['id']}/audit-events"
        )

    assert timeline.status_code == 200
    events = timeline.json()["events"]
    assert len(events) == 1
    event = events[0]
    assert event["version_id"] is None
    assert event["event_type"] == "create"
    assert event["actor_ref"] == "actor.data_preparer.domain_owner"
    assert event["actor_role"] == "data_preparer"
    assert event["reason"] == "登记 Pilot 项目并保留来源边界。"
    assert event["request_id"] == first.headers["X-Request-ID"]
    assert event["idempotency_key_hash"] == hashlib.sha256(key.encode()).hexdigest()
    assert event["event_payload"] == {
        "entity_type": "program",
        "official_name": "MSc Computer Science",
        "institution_name": "The University of Edinburgh",
    }
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


def test_duplicate_official_url_with_another_key_is_rejected(program_database) -> None:
    _, _, sessions = program_database
    with _client(sessions, SequenceIds("program-duplicate"), MutableClock()) as client:
        assert _create_program(client, key="program-first-create-key-0001").status_code == 201
        duplicate_payload = _program_payload()
        duplicate_payload["official_name"] = "A duplicate display name"
        duplicate = client.post(
            f"{INTERNAL}/programs",
            json=duplicate_payload,
            headers=_header("program-second-create-key-0002"),
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "PROGRAM_ALREADY_EXISTS"
    assert duplicate.json()["error"]["request_id"].startswith("req_")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("official_program_url", "http://study.ed.ac.uk/programmes/msc"),
        ("official_program_url", "https://admissions.example.com/programmes/msc"),
    ],
)
def test_program_create_rejects_non_https_and_unregistered_domains(
    program_database, change: str, value: str
) -> None:
    _, _, sessions = program_database
    payload = _program_payload()
    payload[change] = value
    with _client(sessions, SequenceIds("program-invalid"), MutableClock()) as client:
        response = client.post(
            f"{INTERNAL}/programs",
            json=payload,
            headers=_header("program-invalid-create-key-0001"),
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 0


def test_program_create_rejects_extra_fields(program_database) -> None:
    _, _, sessions = program_database
    payload = _program_payload()
    payload["unreviewed_scrape"] = {"should": "not be stored"}
    with _client(sessions, SequenceIds("program-extra"), MutableClock()) as client:
        response = client.post(
            f"{INTERNAL}/programs",
            json=payload,
            headers=_header("program-extra-create-key-0001"),
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 0


def test_evidence_can_be_read_by_id_and_listed_with_dynamic_freshness(
    program_database,
) -> None:
    _, _, sessions = program_database
    clock = MutableClock()
    ids = SequenceIds("program-evidence")
    with _client(sessions, ids, clock) as client:
        program_id = _create_program(
            client, key="program-evidence-create-key-0001"
        ).json()["id"]
        later = _evidence_payload(
            program_id,
            "evidence.program.later",
            captured_at="2026-09-01T08:00:00Z",
            review_due_at="2026-09-20T00:00:00Z",
            expires_at="2026-09-27T00:00:00Z",
            hash_character="a",
        )
        earlier = _evidence_payload(
            program_id,
            "evidence.program.earlier",
            captured_at="2026-08-31T08:00:00Z",
            review_due_at="2026-09-05T00:00:00Z",
            expires_at="2026-09-10T00:00:00Z",
            hash_character="b",
        )
        for payload, key in (
            (later, "program-later-evidence-key-0002"),
            (earlier, "program-earlier-evidence-key-0003"),
        ):
            response = client.post(
                f"{INTERNAL}/source-evidence", json=payload, headers=_header(key)
            )
            assert response.status_code == 201

        by_id = client.get(f"{INTERNAL}/source-evidence/{earlier['id']}")
        listed_fresh = client.get(
            f"{INTERNAL}/programs/{program_id}/source-evidence"
        )
        clock.current = datetime(2026, 9, 6, tzinfo=timezone.utc)
        listed_review_due = client.get(
            f"{INTERNAL}/programs/{program_id}/source-evidence"
        )

    assert by_id.status_code == 200
    assert by_id.json()["snapshot_sha256"] == "b" * 64
    assert by_id.json()["excerpt"] == earlier["excerpt"]
    assert listed_fresh.status_code == 200
    assert listed_fresh.json()["program_id"] == program_id
    fresh_records = listed_fresh.json()["evidence"]
    assert [record["id"] for record in fresh_records] == [
        "evidence.program.earlier",
        "evidence.program.later",
    ]
    assert [record["freshness"] for record in fresh_records] == ["fresh", "fresh"]
    assert [record["freshness"] for record in listed_review_due.json()["evidence"]] == [
        "review_due",
        "fresh",
    ]
    assert set(fresh_records[0]) == {
        "id",
        "program_id",
        "source_type",
        "url",
        "official_domain",
        "page_title",
        "excerpt",
        "snapshot_sha256",
        "source_version",
        "captured_at",
        "verified_at",
        "verified_by",
        "review_due_at",
        "expires_at",
        "availability_at_verification",
        "created_at",
        "freshness",
    }


def test_evidence_read_endpoints_return_stable_not_found_errors(
    program_database,
) -> None:
    _, _, sessions = program_database
    with _client(sessions, SequenceIds("program-missing"), MutableClock()) as client:
        missing_evidence = client.get(
            f"{INTERNAL}/source-evidence/evidence.missing"
        )
        missing_program = client.get(
            f"{INTERNAL}/programs/program.missing/source-evidence"
        )

    for response, code in (
        (missing_evidence, "EVIDENCE_NOT_FOUND"),
        (missing_program, "PROGRAM_NOT_FOUND"),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["request_id"].startswith("req_")
        assert "sqlite" not in response.text.lower()


def test_program_audit_and_evidence_reads_survive_restart(program_database) -> None:
    url, first_engine, first_sessions = program_database
    clock = MutableClock()
    payload: dict | None = None
    program_id = ""
    with _client(first_sessions, SequenceIds("program-restart-first"), clock) as client:
        program_id = _create_program(
            client, key="program-restart-create-key-0001"
        ).json()["id"]
        payload = _evidence_payload(
            program_id,
            "evidence.program.restart",
            captured_at="2026-09-01T08:00:00Z",
            review_due_at="2026-09-20T00:00:00Z",
            expires_at="2026-09-27T00:00:00Z",
            hash_character="c",
        )
        created = client.post(
            f"{INTERNAL}/source-evidence",
            json=payload,
            headers=_header("program-restart-evidence-key-0002"),
        )
        assert created.status_code == 201
        first_timeline = client.get(
            f"{INTERNAL}/programs/{program_id}/audit-events"
        ).json()
        first_evidence = client.get(
            f"{INTERNAL}/source-evidence/{payload['id']}"
        ).json()
    first_engine.dispose()

    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    with _client(
        second_sessions, SequenceIds("program-restart-second"), clock
    ) as client:
        restored_timeline = client.get(
            f"{INTERNAL}/programs/{program_id}/audit-events"
        ).json()
        restored_evidence = client.get(
            f"{INTERNAL}/source-evidence/{payload['id']}"
        ).json()

    assert restored_timeline == first_timeline
    assert restored_evidence == first_evidence
    with second_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Program)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 1
    second_engine.dispose()
