from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import backend.tests.test_phase4_quality_scanner as quality_support
from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.app.schemas.program_fields import ProgramDirection
from backend.app.schemas.version_workflow import SubmitVersionCommand
from backend.app.services.alpha_candidate_importer import AlphaCandidateImporter
from backend.app.services.version_workflow import VersionWorkflowService


FIXED_NOW = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def review_pilot(tmp_path):
    context = quality_support._build_quality_root(tmp_path / "alpha-review-root")
    entry = next(
        item
        for item in context.manifest.programs
        if item.primary_direction == ProgramDirection.LOW_ALTITUDE_ECONOMY
    )
    pack = context.packs_by_ref[entry.pack_ref]
    database_url = f"sqlite:///{tmp_path / 'phase4-review.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    ids = quality_support.SequenceIds("phase4-review")
    with sessions.begin() as session:
        imported = AlphaCandidateImporter(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=ids,
        ).import_pack(
            pack=pack,
            scope=context.scope,
            idempotency_key="phase4-review-pilot-import-key",
        )
        VersionWorkflowService(
            session,
            clock=lambda: FIXED_NOW,
            id_factory=ids,
        ).submit(
            imported.candidate_version_id,
            SubmitVersionCommand(
                submitted_by="actor.data_preparer.codex",
                submission_note="Submit one synthetic Phase 4 review Pilot.",
                request_id="request.phase4.review.submit",
            ),
        )

    app = create_app(
        Settings(_env_file=None, model_api_key=None),
        phase3_session_factory=sessions,
        phase3_clock=lambda: FIXED_NOW,
        phase3_id_factory=ids,
        phase4_quality_context_provider=lambda _dataset_id: context,
    )
    yield app, sessions, context, entry, imported.candidate_version_id
    engine.dispose()


def _review_detail_path(context, entry) -> str:
    return (
        f"/api/v1/internal/alpha-datasets/{context.manifest.dataset_id}"
        f"/programs/{entry.pack_ref}"
    )


def _post(client: TestClient, path: str, body: dict, key: str):
    return client.post(path, json=body, headers={"Idempotency-Key": key})


def test_phase4_page_assets_expose_single_program_manual_review_boundary() -> None:
    app = create_app(Settings(_env_file=None, model_api_key=None))
    with TestClient(app) as client:
        page = client.get("/phase4")
        css = client.get("/static/phase4.css")
        script = client.get("/static/phase4.js")

    assert page.status_code == 200
    assert css.status_code == 200
    assert script.status_code == 200
    assert "先看原文" in page.text
    assert "人工数据质检 · 无抓取 · 无模型 · 无推荐 · 非正式运营后台" in page.text
    assert "一次只核对一个冻结 Program Pack" in page.text
    assert "Actor ref 是审计字段，不代表真实登录身份" in page.text
    assert 'id="fieldRuler"' in page.text
    assert 'id="evidenceList"' in page.text
    assert 'id="gateList"' in page.text
    assert 'id="publishButton"' in page.text
    assert 'id="rejectButton"' in page.text

    for endpoint in (
        "/api/v1/internal/alpha-datasets/",
        "/programs?offset=0&limit=30",
        "/api/v1/internal/program-versions/",
        'decide("publish")',
        'decide("reject")',
    ):
        assert endpoint in script.text
    assert "Idempotency-Key" in script.text
    assert "sessionStorage" in script.text
    assert "const versioned = state.programs.find(item => item.version_id)" in script.text
    assert "fetch(item.url" not in script.text
    assert "/api/v1/profile-analysis" not in script.text
    assert "MODEL_API_KEY" not in script.text


def test_phase4_page_has_mobile_overflow_accessibility_and_motion_guards() -> None:
    app = create_app(Settings(_env_file=None, model_api_key=None))
    with TestClient(app) as client:
        page = client.get("/phase4").text
        css = client.get("/static/phase4.css").text

    assert 'class="skip-link"' in page
    assert 'role="alert"' in page
    assert 'aria-live="polite"' in page
    assert "@media (max-width: 760px)" in css
    assert "@media (max-width: 430px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
    assert "overflow-wrap: anywhere" in css
    assert "grid-template-columns: minmax(0, 1fr)" in css
    assert 'href="data:,"' in page


def test_review_list_is_paginated_stable_and_only_reads_frozen_context(
    review_pilot,
) -> None:
    app, _, context, entry, version_id = review_pilot
    path = f"/api/v1/internal/alpha-datasets/{context.manifest.dataset_id}/programs"
    with TestClient(app, raise_server_exceptions=False) as client:
        first = client.get(path, params={"offset": 0, "limit": 7})
        second = client.get(path, params={"offset": 0, "limit": 7})
        invalid = client.get(path, params={"offset": 0, "limit": 31})

    assert first.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["schema_version"] == "alpha_review_program_list.v1"
    assert body["total"] == 20
    assert body["limit"] == 7
    assert len(body["programs"]) == 7
    assert [item["pack_ref"] for item in body["programs"]] == sorted(
        item["pack_ref"] for item in body["programs"]
    )
    selected = next(
        item for item in body["programs"] if item["pack_ref"] == entry.pack_ref
    )
    assert selected["version_id"] == version_id
    assert selected["status"] == "pending_review"
    assert invalid.status_code == 422


def test_review_detail_exposes_fields_evidence_diff_and_all_preflight_gates(
    review_pilot,
) -> None:
    app, _, context, entry, version_id = review_pilot
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(_review_detail_path(context, entry))

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "alpha_review_program_detail.v1"
    assert body["program"]["pack_ref"] == entry.pack_ref
    assert body["version"]["version_id"] == version_id
    assert body["version"]["status"] == "pending_review"
    assert body["expected_field_count"] == 16
    assert len(body["fields"]) == 16
    assert body["critical_field_count"] == 11
    assert body["reviewed_field_count"] == 0
    assert body["preflight_ready"] is True
    assert body["can_publish"] is True
    assert body["can_reject"] is True
    assert len(body["gates"]) == 8
    assert {gate["status"] for gate in body["gates"]} == {"pass", "pending"}
    assert next(
        gate for gate in body["gates"] if gate["name"] == "four_eye_review_rate"
    )["status"] == "pending"
    low_field = next(
        field
        for field in body["fields"]
        if field["field_key"] == "taxonomy.low_altitude_basis"
    )
    assert low_field["diff"]["change_type"] == "added"
    assert low_field["coverage_status"] == "confirmed"
    assert any(
        item["reviewed_source_role"] == "curriculum"
        and item["support_scope"] == "direct"
        and "Autonomous Flight Systems" in item["excerpt"]
        for item in low_field["evidence"]
    )
    assert all(item["freshness"] == "fresh" for item in low_field["evidence"])


def test_page_publish_action_reuses_workflow_and_refreshes_all_eight_gates(
    review_pilot,
) -> None:
    app, _, context, entry, version_id = review_pilot
    detail_path = _review_detail_path(context, entry)
    with TestClient(app, raise_server_exceptions=False) as client:
        publish = _post(
            client,
            f"/api/v1/internal/program-versions/{version_id}/publish",
            {
                "reviewed_by": "actor.domain_reviewer.product_owner",
                "review_note": "已逐项核对合成 Pilot 的关键字段、官方原文、diff 与全部门禁。",
                "expected_current_version_id": None,
            },
            "phase4-page-publish-key-0001",
        )
        detail = client.get(detail_path)
        public = client.get(f"/api/v1/programs/{entry.program_ref}/published")

    assert publish.status_code == 200
    assert detail.status_code == 200
    body = detail.json()
    assert body["version"]["status"] == "published"
    assert body["current_published_version_id"] == version_id
    assert body["preflight_ready"] is False
    assert body["can_publish"] is False
    assert body["can_reject"] is False
    assert {gate["status"] for gate in body["gates"]} == {"pass"}
    assert public.status_code == 200
    assert public.json()["version_id"] == version_id


def test_page_reject_action_keeps_published_only_empty(review_pilot) -> None:
    app, _, context, entry, version_id = review_pilot
    with TestClient(app, raise_server_exceptions=False) as client:
        rejected = _post(
            client,
            f"/api/v1/internal/program-versions/{version_id}/reject",
            {
                "reviewed_by": "actor.domain_reviewer.product_owner",
                "review_note": "合成验收：发现字段与官方原文不一致，驳回返工。",
            },
            "phase4-page-reject-key-0001",
        )
        detail = client.get(_review_detail_path(context, entry))
        public = client.get(f"/api/v1/programs/{entry.program_ref}/published")

    assert rejected.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["version"]["status"] == "rejected"
    assert detail.json()["can_publish"] is False
    assert detail.json()["can_reject"] is False
    assert public.status_code == 404
    assert public.json()["error"]["code"] == "PROGRAM_NOT_PUBLISHED"


def test_review_api_errors_are_safe_and_do_not_leak_local_paths(review_pilot) -> None:
    app, _, context, _, _ = review_pilot
    with TestClient(app, raise_server_exceptions=False) as client:
        missing_pack = client.get(
            f"/api/v1/internal/alpha-datasets/{context.manifest.dataset_id}"
            "/programs/pack.synthetic.does-not-exist"
        )
        missing_dataset = client.get(
            "/api/v1/internal/alpha-datasets/dataset.alpha.unknown/programs"
        )

    assert missing_pack.status_code == 404
    assert missing_pack.json()["error"]["code"] == "ALPHA_PROGRAM_NOT_FOUND"
    assert missing_dataset.status_code == 404
    assert missing_dataset.json()["error"]["code"] == "ALPHA_DATASET_NOT_FOUND"
    serialized = f"{missing_pack.text}\n{missing_dataset.text}"
    assert str(context) not in serialized
    assert "/Users/" not in serialized
    assert "sqlite" not in serialized.lower()
