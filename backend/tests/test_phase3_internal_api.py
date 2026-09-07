from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import backend.tests.test_phase3_candidates as candidate_support
import backend.tests.test_phase3_idempotency as idempotency_support
import backend.tests.test_phase3_version_workflow as workflow_support
from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.models import (
    AuditEvent,
    IdempotencyRecord,
    Program,
    ProgramPublication,
    ProgramRegion,
    ProgramVersion,
    SourceEvidence,
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
INTERNAL = "/api/v1/internal"


@pytest.fixture
def api_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'phase3-api.sqlite3'}"
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
    settings = Settings(_env_file=None, model_api_key=None)
    app = create_app(
        settings,
        phase3_session_factory=sessions,
        phase3_clock=lambda: FIXED_NOW,
        phase3_id_factory=ids,
    )
    return TestClient(app, raise_server_exceptions=False)


def _header(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


def _evidence_json(evidence_id: str, snapshot_hash: str) -> dict:
    return idempotency_support._evidence_payload(
        evidence_id, snapshot_hash
    ).model_dump(mode="json")


def _candidate_json(**overrides) -> dict:
    body = candidate_support._candidate_payload(**overrides).model_dump(mode="json")
    body.pop("request_id")
    return body


def _submit_json(actor: str = "actor.data_preparer.codex") -> dict:
    command = workflow_support._submit_command(actor=actor).model_dump(mode="json")
    command.pop("request_id")
    return command


def _publish_json(
    expected_current_version_id: str | None,
    actor: str = "actor.domain_reviewer.product_owner",
) -> dict:
    command = workflow_support._publish_command(
        expected_current_version_id, actor=actor
    ).model_dump(mode="json")
    command.pop("request_id")
    return command


def _reject_json() -> dict:
    command = workflow_support._reject_command().model_dump(mode="json")
    command.pop("request_id")
    return command


def _post_evidence(client: TestClient, evidence_id: str, hash_character: str, key: str):
    return client.post(
        f"{INTERNAL}/source-evidence",
        json=_evidence_json(evidence_id, hash_character * 64),
        headers=_header(key),
    )


def test_internal_api_runs_real_evidence_version_review_and_rollback_chain(
    api_database,
) -> None:
    _, _, sessions = api_database
    ids = SequenceIds("api-chain")
    with _client(sessions, ids) as client:
        evidence_responses = [
            _post_evidence(client, E1, "1", "api-evidence-e1-key-0001"),
            _post_evidence(client, E2, "2", "api-evidence-e2-key-0002"),
            _post_evidence(client, E3, "3", "api-evidence-e3-key-0003"),
        ]
        assert [response.status_code for response in evidence_responses] == [201, 201, 201]
        replayed_e1 = _post_evidence(
            client, E1, "1", "api-evidence-e1-key-0001"
        )
        assert replayed_e1.status_code == 201
        assert replayed_e1.json() == evidence_responses[0].json()

        v1_body = _candidate_json()
        v1_response = client.post(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions",
            json=v1_body,
            headers=_header("api-v1-create-key-0004"),
        )
        assert v1_response.status_code == 201
        v1 = v1_response.json()
        replayed_v1 = client.post(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions",
            json=v1_body,
            headers=_header("api-v1-create-key-0004"),
        )
        assert replayed_v1.json() == v1

        submit_v1 = client.post(
            f"{INTERNAL}/program-versions/{v1['id']}/submit",
            json=_submit_json(),
            headers=_header("api-v1-submit-key-0005"),
        )
        assert submit_v1.status_code == 200
        replayed_submit = client.post(
            f"{INTERNAL}/program-versions/{v1['id']}/submit",
            json=_submit_json(),
            headers=_header("api-v1-submit-key-0005"),
        )
        assert replayed_submit.json() == submit_v1.json()
        publish_v1 = client.post(
            f"{INTERNAL}/program-versions/{v1['id']}/publish",
            json=_publish_json(None),
            headers=_header("api-v1-publish-key-0006"),
        )
        assert publish_v1.status_code == 200
        replayed_publish = client.post(
            f"{INTERNAL}/program-versions/{v1['id']}/publish",
            json=_publish_json(None),
            headers=_header("api-v1-publish-key-0006"),
        )
        assert replayed_publish.json() == publish_v1.json()

        v2_response = client.post(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions",
            json=_candidate_json(
                base_version_id=v1["id"],
                request_id="request.candidate.v2",
            ),
            headers=_header("api-v2-create-key-0007"),
        )
        v2 = v2_response.json()
        assert v2_response.status_code == 201
        assert client.post(
            f"{INTERNAL}/program-versions/{v2['id']}/submit",
            json=_submit_json(),
            headers=_header("api-v2-submit-key-0008"),
        ).status_code == 200
        rejected_v2 = client.post(
            f"{INTERNAL}/program-versions/{v2['id']}/reject",
            json=_reject_json(),
            headers=_header("api-v2-reject-key-0009"),
        )
        assert rejected_v2.status_code == 200
        assert rejected_v2.json()["status"] == "rejected"
        assert rejected_v2.json()["current_version_id"] == v1["id"]

        v3_response = client.post(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions",
            json=_candidate_json(
                base_version_id=v1["id"],
                academic_year="2027-28",
                manual_review=True,
                direct_evidence=E3,
                request_id="request.candidate.v3",
            ),
            headers=_header("api-v3-create-key-0010"),
        )
        v3 = v3_response.json()
        assert v3_response.status_code == 201
        assert client.post(
            f"{INTERNAL}/program-versions/{v3['id']}/submit",
            json=_submit_json(),
            headers=_header("api-v3-submit-key-0011"),
        ).status_code == 200
        published_v3 = client.post(
            f"{INTERNAL}/program-versions/{v3['id']}/publish",
            json=_publish_json(v1["id"]),
            headers=_header("api-v3-publish-key-0012"),
        )
        assert published_v3.status_code == 200
        assert published_v3.json()["publication_revision"] == 2

        rollback_body = {
            "target_version_id": v1["id"],
            "expected_current_version_id": v3["id"],
            "created_by": "actor.data_preparer.codex",
            "creation_note": "Restore v1 through a reviewed rollback candidate.",
        }
        rollback_response = client.post(
            f"{INTERNAL}/programs/{PROGRAM_ID}/rollback-candidates",
            json=rollback_body,
            headers=_header("api-rollback-create-key-0013"),
        )
        assert rollback_response.status_code == 201
        rollback = rollback_response.json()
        replayed_rollback = client.post(
            f"{INTERNAL}/programs/{PROGRAM_ID}/rollback-candidates",
            json=rollback_body,
            headers=_header("api-rollback-create-key-0013"),
        )
        assert replayed_rollback.json() == rollback

    assert rollback["status"] == "candidate"
    assert rollback["base_version_id"] == v3["id"]
    assert rollback["rollback_of_version_id"] == v1["id"]
    assert rollback["content_sha256"] == v1["content_sha256"]
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 3
        assert session.scalar(select(func.count()).select_from(ProgramVersion)) == 4
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 10
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 13
        publication = session.get(ProgramPublication, PROGRAM_ID)
        assert publication.current_version_id == v3["id"]
        assert publication.revision == 2
        assert session.get(ProgramVersion, v1["id"]).status == VersionStatus.SUPERSEDED
        assert session.get(ProgramVersion, v2["id"]).status == VersionStatus.REJECTED


def test_internal_api_requires_valid_key_and_maps_conflicts(api_database) -> None:
    _, _, sessions = api_database
    ids = SequenceIds("api-errors")
    payload = _evidence_json(E1, "1" * 64)
    with _client(sessions, ids) as client:
        missing_key = client.post(f"{INTERNAL}/source-evidence", json=payload)
        assert missing_key.status_code == 400
        assert missing_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
        assert missing_key.headers["X-Request-ID"].startswith("req_")

        invalid_key = client.post(
            f"{INTERNAL}/source-evidence",
            json=payload,
            headers=_header("short"),
        )
        assert invalid_key.status_code == 400
        assert invalid_key.json()["error"]["code"] == "IDEMPOTENCY_KEY_INVALID"

        first = client.post(
            f"{INTERNAL}/source-evidence",
            json=payload,
            headers=_header("api-conflict-evidence-key-0001"),
        )
        assert first.status_code == 201
        changed = deepcopy(payload)
        changed["page_title"] = "Different request with the same key"
        conflict = client.post(
            f"{INTERNAL}/source-evidence",
            json=changed,
            headers=_header("api-conflict-evidence-key-0001"),
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

        extra = deepcopy(payload)
        extra["raw_html"] = "<script>must not run</script>"
        invalid_body = client.post(
            f"{INTERNAL}/source-evidence",
            json=extra,
            headers=_header("api-invalid-body-key-0002"),
        )
        assert invalid_body.status_code == 422
        assert invalid_body.json()["error"]["code"] == "INPUT_INVALID"
        assert "traceback" not in invalid_body.text.lower()
        assert "sqlite" not in invalid_body.text.lower()
        assert "source_evidence" not in invalid_body.text.lower()


def test_internal_api_maps_domain_errors_without_leaking_evidence(api_database) -> None:
    _, _, sessions = api_database
    ids = SequenceIds("api-domain-errors")
    wrong_domain_payload = _evidence_json(E1, "1" * 64)
    wrong_domain_payload["url"] = "https://admissions.example.com/private"
    wrong_domain_payload["official_domain"] = "admissions.example.com"
    with _client(sessions, ids) as client:
        response = client.post(
            f"{INTERNAL}/source-evidence",
            json=wrong_domain_payload,
            headers=_header("api-wrong-domain-key-0001"),
        )
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "OFFICIAL_DOMAIN_MISMATCH"
        assert error["request_id"].startswith("req_")
        assert wrong_domain_payload["excerpt"] not in response.text
        assert "programs" not in response.text.lower()

        missing_version = client.post(
            f"{INTERNAL}/program-versions/version.missing/submit",
            json=_submit_json(),
            headers=_header("api-missing-version-key-0002"),
        )
        assert missing_version.status_code == 404
        assert missing_version.json()["error"]["code"] == "VERSION_NOT_FOUND"


def test_candidate_cannot_publish_directly_through_api(api_database) -> None:
    _, _, sessions = api_database
    ids = SequenceIds("api-transition")
    with _client(sessions, ids) as client:
        for evidence_id, character, key in (
            (E1, "1", "api-transition-e1-key-0001"),
            (E2, "2", "api-transition-e2-key-0002"),
        ):
            assert _post_evidence(client, evidence_id, character, key).status_code == 201
        created = client.post(
            f"{INTERNAL}/programs/{PROGRAM_ID}/versions",
            json=_candidate_json(),
            headers=_header("api-transition-candidate-key-0003"),
        ).json()
        response = client.post(
            f"{INTERNAL}/program-versions/{created['id']}/publish",
            json=_publish_json(None),
            headers=_header("api-transition-publish-key-0004"),
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_TRANSITION_INVALID"
    with sessions() as session:
        assert session.get(ProgramVersion, created["id"]).status == VersionStatus.CANDIDATE
        assert session.get(ProgramPublication, PROGRAM_ID) is None


def test_idempotent_http_response_replays_after_app_and_engine_restart(
    api_database,
) -> None:
    url, first_engine, first_sessions = api_database
    payload = _evidence_json(E1, "1" * 64)
    key = "api-restart-evidence-key-0001"
    with _client(first_sessions, SequenceIds("api-restart-first")) as first_client:
        first = first_client.post(
            f"{INTERNAL}/source-evidence",
            json=payload,
            headers=_header(key),
        )
    assert first.status_code == 201
    first_engine.dispose()

    second_engine = create_database_engine(url)
    second_sessions = create_session_factory(second_engine)
    with _client(second_sessions, SequenceIds("api-restart-second")) as second_client:
        replayed = second_client.post(
            f"{INTERNAL}/source-evidence",
            json=payload,
            headers=_header(key),
        )
    assert replayed.status_code == 201
    assert replayed.json() == first.json()
    with second_sessions() as session:
        assert session.scalar(select(func.count()).select_from(SourceEvidence)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
    second_engine.dispose()
