from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

import backend.tests.test_phase3_candidates as candidate_support
import backend.tests.test_phase3_internal_api as api_support
from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    Program,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    VersionStatus,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app


PROGRAM_ID = candidate_support.PROGRAM_ID
E1 = candidate_support.E1
E2 = candidate_support.E2
E3 = candidate_support.E3
FIXED_NOW = candidate_support.FIXED_NOW
SequenceIds = candidate_support.SequenceIds
INTERNAL = api_support.INTERNAL


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def published_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'published-api.sqlite3'}"
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


def _client(sessions, ids, clock: MutableClock) -> TestClient:
    app = create_app(
        Settings(_env_file=None, model_api_key=None),
        phase3_session_factory=sessions,
        phase3_clock=clock,
        phase3_id_factory=ids,
    )
    return TestClient(app, raise_server_exceptions=False)


def _seed_evidence(client: TestClient) -> None:
    for evidence_id, character, key in (
        (E1, "1", "published-e1-key-0001"),
        (E2, "2", "published-e2-key-0002"),
        (E3, "3", "published-e3-key-0003"),
    ):
        response = api_support._post_evidence(
            client, evidence_id, character, key
        )
        assert response.status_code == 201


def _create_candidate(client: TestClient, key: str, **overrides) -> dict:
    response = client.post(
        f"{INTERNAL}/programs/{PROGRAM_ID}/versions",
        json=api_support._candidate_json(**overrides),
        headers=api_support._header(key),
    )
    assert response.status_code == 201
    return response.json()


def _submit(client: TestClient, version_id: str, key: str) -> dict:
    response = client.post(
        f"{INTERNAL}/program-versions/{version_id}/submit",
        json=api_support._submit_json(),
        headers=api_support._header(key),
    )
    assert response.status_code == 200
    return response.json()


def _publish(
    client: TestClient,
    version_id: str,
    current_version_id: str | None,
    key: str,
) -> dict:
    response = client.post(
        f"{INTERNAL}/program-versions/{version_id}/publish",
        json=api_support._publish_json(current_version_id),
        headers=api_support._header(key),
    )
    assert response.status_code == 200
    return response.json()


def _create_and_publish_v1(client: TestClient) -> dict:
    _seed_evidence(client)
    v1 = _create_candidate(client, "published-v1-create-key-0004")
    _submit(client, v1["id"], "published-v1-submit-key-0005")
    _publish(client, v1["id"], None, "published-v1-publish-key-0006")
    return v1


def _get(client: TestClient):
    return client.get(f"/api/v1/programs/{PROGRAM_ID}/published")


def test_missing_or_candidate_only_program_returns_no_private_snapshot(
    published_database,
) -> None:
    _, _, sessions = published_database
    ids = SequenceIds("not-published")
    clock = MutableClock(FIXED_NOW)
    with _client(sessions, ids, clock) as client:
        missing = client.get("/api/v1/programs/program.missing/published")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "PROGRAM_NOT_FOUND"

        before_candidate = _get(client)
        assert before_candidate.status_code == 404
        assert before_candidate.json()["error"]["code"] == "PROGRAM_NOT_PUBLISHED"

        _seed_evidence(client)
        candidate = _create_candidate(
            client, "not-published-candidate-key-0004"
        )
        candidate_only = _get(client)

    assert candidate_only.status_code == 404
    assert candidate_only.json()["error"]["code"] == "PROGRAM_NOT_PUBLISHED"
    assert candidate["id"] not in candidate_only.text
    assert candidate["content_sha256"] not in candidate_only.text
    assert candidate["fields"][0]["display_text"] not in candidate_only.text


def test_public_read_returns_only_current_across_pending_rejected_and_published(
    published_database,
) -> None:
    _, _, sessions = published_database
    ids = SequenceIds("isolation")
    clock = MutableClock(FIXED_NOW)
    with _client(sessions, ids, clock) as client:
        v1 = _create_and_publish_v1(client)
        public_v1_response = _get(client)
        assert public_v1_response.status_code == 200
        public_v1 = public_v1_response.json()

        v2 = _create_candidate(
            client,
            "isolation-v2-create-key-0007",
            base_version_id=v1["id"],
            academic_year="2027-28",
            manual_review=True,
            direct_evidence=E3,
            request_id="request.isolation.v2",
        )
        _submit(client, v2["id"], "isolation-v2-submit-key-0008")
        while_pending = _get(client)
        assert while_pending.status_code == 200
        assert while_pending.json() == public_v1
        assert v2["id"] not in while_pending.text
        assert v2["content_sha256"] not in while_pending.text

        rejected = client.post(
            f"{INTERNAL}/program-versions/{v2['id']}/reject",
            json=api_support._reject_json(),
            headers=api_support._header("isolation-v2-reject-key-0009"),
        )
        assert rejected.status_code == 200
        after_reject = _get(client)
        assert after_reject.json() == public_v1

        v3 = _create_candidate(
            client,
            "isolation-v3-create-key-0010",
            base_version_id=v1["id"],
            academic_year="2027-28",
            manual_review=True,
            direct_evidence=E3,
            request_id="request.isolation.v3",
        )
        _submit(client, v3["id"], "isolation-v3-submit-key-0011")
        _publish(
            client,
            v3["id"],
            v1["id"],
            "isolation-v3-publish-key-0012",
        )
        public_v3_response = _get(client)

    assert public_v1["program_id"] == PROGRAM_ID
    assert public_v1["version_id"] == v1["id"]
    assert public_v1["version_no"] == 1
    assert public_v1["content_sha256"] == v1["content_sha256"]
    assert public_v1["fields"][0]["value_payload"]["applicable_academic_year"] == "2026-27"
    assert [citation["evidence_id"] for citation in public_v1["fields"][0]["evidence"]] == [E1, E2]
    assert [citation["support_scope"] for citation in public_v1["fields"][0]["evidence"]] == ["direct", "definition"]
    assert all(
        citation["freshness"] == "fresh"
        for citation in public_v1["fields"][0]["evidence"]
    )
    assert all(
        citation["verified_at"] == "2026-09-01T00:00:00Z"
        for citation in public_v1["fields"][0]["evidence"]
    )
    assert "submitted_by" not in public_v1
    assert "reviewed_by" not in public_v1

    public_v3 = public_v3_response.json()
    assert public_v3_response.status_code == 200
    assert public_v3["version_id"] == v3["id"]
    assert public_v3["content_sha256"] == v3["content_sha256"]
    assert public_v3["fields"][0]["value_payload"]["applicable_academic_year"] == "2027-28"
    assert v1["id"] not in public_v3_response.text
    assert v2["id"] not in public_v3_response.text


def test_public_freshness_is_derived_at_read_time(published_database) -> None:
    _, _, sessions = published_database
    ids = SequenceIds("freshness")
    clock = MutableClock(FIXED_NOW)
    with _client(sessions, ids, clock) as client:
        _create_and_publish_v1(client)
        assert all(
            citation["freshness"] == "fresh"
            for citation in _get(client).json()["fields"][0]["evidence"]
        )
        clock.now = FIXED_NOW + timedelta(days=30)
        review_due = _get(client)
        assert review_due.status_code == 200
        assert all(
            citation["freshness"] == "review_due"
            for citation in review_due.json()["fields"][0]["evidence"]
        )
        clock.now = FIXED_NOW + timedelta(days=38)
        expired = _get(client)

    assert expired.status_code == 200
    assert all(
        citation["freshness"] == "expired"
        for citation in expired.json()["fields"][0]["evidence"]
    )


def test_invalid_pointer_and_content_hash_fail_closed_without_history_fallback(
    published_database,
) -> None:
    _, _, sessions = published_database
    ids = SequenceIds("integrity")
    clock = MutableClock(FIXED_NOW)
    with _client(sessions, ids, clock) as client:
        v1 = _create_and_publish_v1(client)
        v2 = _create_candidate(
            client,
            "integrity-v2-create-key-0007",
            base_version_id=v1["id"],
            academic_year="2027-28",
            manual_review=True,
            direct_evidence=E3,
            request_id="request.integrity.v2",
        )
        _submit(client, v2["id"], "integrity-v2-submit-key-0008")
        with sessions.begin() as session:
            publication = session.get(ProgramPublication, PROGRAM_ID)
            publication.current_version_id = v2["id"]
        invalid_pointer = _get(client)
        assert invalid_pointer.status_code == 409
        assert invalid_pointer.json()["error"]["code"] == "PUBLICATION_INTEGRITY_ERROR"
        assert v1["id"] not in invalid_pointer.text
        assert v2["id"] not in invalid_pointer.text

        with sessions.begin() as session:
            publication = session.get(ProgramPublication, PROGRAM_ID)
            publication.current_version_id = v1["id"]
            session.execute(
                update(ProgramVersion)
                .where(ProgramVersion.id == v1["id"])
                .values(content_sha256="f" * 64)
            )
        invalid_hash = _get(client)

    assert invalid_hash.status_code == 409
    assert invalid_hash.json()["error"]["code"] == "PUBLICATION_INTEGRITY_ERROR"
    assert "program_versions" not in invalid_hash.text
    assert "sqlite" not in invalid_hash.text.lower()


def test_published_response_survives_app_and_engine_restart(
    published_database,
) -> None:
    url, first_engine, first_sessions = published_database
    clock = MutableClock(FIXED_NOW)
    with _client(first_sessions, SequenceIds("read-restart-first"), clock) as client:
        _create_and_publish_v1(client)
        first = _get(client)
    assert first.status_code == 200
    first_engine.dispose()

    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    with _client(second_sessions, SequenceIds("read-restart-second"), clock) as client:
        restored = _get(client)

    assert restored.status_code == 200
    assert restored.json() == first.json()
    assert restored.json()["content_sha256"] == first.json()["content_sha256"]
    second_engine.dispose()
