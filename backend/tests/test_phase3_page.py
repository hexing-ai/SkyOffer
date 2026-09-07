from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import backend.tests.test_phase3_candidates as candidate_support
import backend.tests.test_phase3_internal_api as api_support
from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app


def test_phase3_page_exposes_fixed_manual_acceptance_workflow() -> None:
    app = create_app(Settings(_env_file=None, model_api_key=None))
    with TestClient(app) as client:
        page = client.get("/phase3")
        stylesheet = client.get("/static/phase3.css")
        script = client.get("/static/phase3.js")

    assert page.status_code == 200
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert "v1 → v2 → rollback v3" in page.text
    assert "人工录入 · 无抓取 · 无模型 · 非正式运营后台" in page.text
    assert "不判断录取概率" in page.text
    assert "Actor ref 仅用于第三阶段审计，不代表账号认证" in page.text
    assert 'id="stepList"' in page.text
    assert 'id="publishedView"' in page.text
    assert 'id="auditTimeline"' in page.text

    assert script.text.count("id: \"") >= 10
    for endpoint in (
        "/api/v1/internal/programs",
        "/api/v1/internal/source-evidence",
        "/versions",
        "/submit",
        "/publish",
        "/rollback-candidates",
        "/audit-events",
        "/api/v1/programs/",
    ):
        assert endpoint in script.text
    assert "Idempotency-Key" in script.text
    assert "localStorage" in script.text
    assert "version.base_version_id" in script.text
    assert "version.rollback_of_version_id" in script.text
    assert "/api/v1/profile-analysis" not in script.text
    assert "MODEL_API_KEY" not in script.text


def test_phase3_page_has_mobile_and_accessibility_guards() -> None:
    app = create_app(Settings(_env_file=None, model_api_key=None))
    with TestClient(app) as client:
        page = client.get("/phase3").text
        stylesheet = client.get("/static/phase3.css").text

    assert 'class="skip-link"' in page
    assert 'role="alert"' in page
    assert "@media (max-width: 680px)" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ":focus-visible" in stylesheet
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in stylesheet
    assert ".readout-card { min-width: 0" in stylesheet
    assert "grid-template-columns: minmax(0, 1fr)" in stylesheet
    assert 'href="data:,"' in page


def test_phase3_page_workflow_contract_completes_real_v1_v2_rollback_chain(
    tmp_path,
) -> None:
    url = f"sqlite:///{tmp_path / 'phase3-page.sqlite3'}"
    upgrade_database(url)
    engine = create_database_engine(url)
    sessions = create_session_factory(engine)
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    app = create_app(
        Settings(_env_file=None, model_api_key=None),
        phase3_session_factory=sessions,
        phase3_clock=lambda: now,
        phase3_id_factory=candidate_support.SequenceIds("page-chain"),
    )
    program_payload = {
        "official_name": "Computer Science MSc",
        "institution_name": "The University of Edinburgh",
        "region": "united_kingdom",
        "official_program_url": (
            "https://study.ed.ac.uk/programmes/postgraduate-taught/"
            "110-computer-science?skyoffer_phase3_scenario=pagechain"
        ),
        "registered_official_domain": "ed.ac.uk",
        "created_by": "actor.data_preparer.codex",
        "creation_note": "Phase 3 page acceptance contract.",
    }
    evidence_ids = {
        "e1": "evidence.phase3.pagechain.e1",
        "e2": "evidence.phase3.pagechain.e2",
        "e3": "evidence.phase3.pagechain.e3",
    }

    def post(client, path: str, body: dict, key: str):
        return client.post(
            path,
            json=body,
            headers={"Idempotency-Key": key},
        )

    def candidate_body(**overrides) -> dict:
        body = candidate_support._candidate_payload(**overrides).model_dump(
            mode="json"
        )
        body.pop("request_id")
        return body

    with TestClient(app, raise_server_exceptions=False) as client:
        program_response = post(
            client,
            "/api/v1/internal/programs",
            program_payload,
            "page-program-create-key-0001",
        )
        assert program_response.status_code == 201
        program_id = program_response.json()["id"]

        for index, (slot, evidence_id) in enumerate(evidence_ids.items(), start=2):
            body = api_support._evidence_json(evidence_id, str(index) * 64)
            body["program_id"] = program_id
            body["url"] = (
                "https://study.ed.ac.uk/programmes/postgraduate-taught/"
                f"110-computer-science?evidence={slot}"
            )
            body["captured_at"] = now.isoformat()
            body["verified_at"] = now.isoformat()
            body["review_due_at"] = (now + timedelta(days=30)).isoformat()
            body["expires_at"] = (now + timedelta(days=37)).isoformat()
            assert post(
                client,
                "/api/v1/internal/source-evidence",
                body,
                f"page-evidence-{slot}-key-000{index}",
            ).status_code == 201

        v1 = post(
            client,
            f"/api/v1/internal/programs/{program_id}/versions",
            candidate_body(
                direct_evidence=evidence_ids["e1"],
                policy_evidence=evidence_ids["e2"],
            ),
            "page-v1-create-key-0005",
        ).json()
        assert client.get(
            f"/api/v1/programs/{program_id}/published"
        ).status_code == 404
        assert post(
            client,
            f"/api/v1/internal/program-versions/{v1['id']}/submit",
            api_support._submit_json(),
            "page-v1-submit-key-0006",
        ).status_code == 200
        assert client.get(
            f"/api/v1/programs/{program_id}/published"
        ).status_code == 404
        assert post(
            client,
            f"/api/v1/internal/program-versions/{v1['id']}/publish",
            api_support._publish_json(None),
            "page-v1-publish-key-0007",
        ).status_code == 200
        published_v1 = client.get(
            f"/api/v1/programs/{program_id}/published"
        ).json()

        v2 = post(
            client,
            f"/api/v1/internal/programs/{program_id}/versions",
            candidate_body(
                base_version_id=v1["id"],
                academic_year="2027-28",
                manual_review=True,
                direct_evidence=evidence_ids["e3"],
                policy_evidence=evidence_ids["e2"],
                request_id="request.page.v2",
            ),
            "page-v2-create-key-0008",
        ).json()
        assert client.get(
            f"/api/v1/programs/{program_id}/published"
        ).json()["version_id"] == v1["id"]
        assert post(
            client,
            f"/api/v1/internal/program-versions/{v2['id']}/submit",
            api_support._submit_json(),
            "page-v2-submit-key-0009",
        ).status_code == 200
        assert client.get(
            f"/api/v1/programs/{program_id}/published"
        ).json()["version_id"] == v1["id"]
        assert post(
            client,
            f"/api/v1/internal/program-versions/{v2['id']}/publish",
            api_support._publish_json(v1["id"]),
            "page-v2-publish-key-0010",
        ).status_code == 200
        published_v2 = client.get(
            f"/api/v1/programs/{program_id}/published"
        ).json()

        v3 = post(
            client,
            f"/api/v1/internal/programs/{program_id}/rollback-candidates",
            {
                "target_version_id": v1["id"],
                "expected_current_version_id": v2["id"],
                "created_by": "actor.data_preparer.codex",
                "creation_note": "Create reviewed rollback v3.",
            },
            "page-v3-create-key-0011",
        ).json()
        assert client.get(
            f"/api/v1/programs/{program_id}/published"
        ).json()["version_id"] == v2["id"]
        assert post(
            client,
            f"/api/v1/internal/program-versions/{v3['id']}/submit",
            api_support._submit_json(),
            "page-v3-submit-key-0012",
        ).status_code == 200
        assert client.get(
            f"/api/v1/programs/{program_id}/published"
        ).json()["version_id"] == v2["id"]
        assert post(
            client,
            f"/api/v1/internal/program-versions/{v3['id']}/publish",
            api_support._publish_json(v2["id"]),
            "page-v3-publish-key-0013",
        ).status_code == 200
        published_v3 = client.get(
            f"/api/v1/programs/{program_id}/published"
        ).json()
        history = client.get(
            f"/api/v1/internal/programs/{program_id}/versions"
        ).json()["versions"]
        audit = client.get(
            f"/api/v1/internal/programs/{program_id}/audit-events"
        ).json()["events"]

    assert published_v1["fields"][0]["value_payload"][
        "applicable_academic_year"
    ] == "2026-27"
    assert published_v2["fields"][0]["value_payload"][
        "applicable_academic_year"
    ] == "2027-28"
    assert published_v3["version_id"] == v3["id"]
    assert published_v3["content_sha256"] == published_v1["content_sha256"]
    assert [version["status"] for version in history] == [
        "superseded",
        "superseded",
        "published",
    ]
    assert v3["base_version_id"] == v2["id"]
    assert v3["rollback_of_version_id"] == v1["id"]
    assert len(audit) == 10
    assert audit[0]["event_payload"]["entity_type"] == "program"
    assert all(event["request_id"].startswith("req_") for event in audit)
    engine.dispose()
