from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.program_catalog import ProgramCatalogService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALPHA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
FIXED_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _client() -> TestClient:
    service = ProgramCatalogService(alpha_root=ALPHA_ROOT, clock=lambda: FIXED_NOW)
    return TestClient(
        create_app(
            settings=Settings(model_api_key="test"),
            program_catalog_service=service,
        ),
        raise_server_exceptions=False,
    )


def test_lists_twenty_candidate_only_programs_without_claiming_publication():
    with _client() as client:
        response = client.get("/api/v1/programs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "program_catalog_list.v1"
    assert payload["dataset"]["program_count"] == 20
    assert payload["dataset"]["data_boundary"] == "internal_candidate_only"
    assert payload["dataset"]["public_publishable"] is False
    assert len(payload["programs"]) == 20
    assert all(item["review_status"] == "domain_reviewed" for item in payload["programs"])
    assert {item["coverage"]["total"] for item in payload["programs"]} == {15, 16}


def test_detail_exposes_field_level_official_evidence_and_version():
    program_ref = "program.uk.manchester.msc_aerospace_engineering"
    with _client() as client:
        response = client.get(f"/api/v1/programs/{program_ref}")

    assert response.status_code == 200
    payload = response.json()
    program = payload["program"]
    assert payload["schema_version"] == "program_catalog_detail.v1"
    assert program["candidate_version_id"] == "version.phase4.batch8.7.1"
    assert len(program["fields"]) == 15
    language = next(
        field for field in program["fields"] if field["field_key"] == "requirements.language"
    )
    assert language["label"] == "语言要求"
    assert language["coverage_status"] == "confirmed"
    assert language["citations"][0]["url"].startswith("https://www.manchester.ac.uk/")
    assert language["citations"][0]["verified_at"] == "2026-09-03T14:15:00Z"
    assert language["citations"][0]["freshness"] == "fresh"


def test_missing_program_is_a_stable_404():
    with _client() as client:
        response = client.get("/api/v1/programs/program.hk.missing.example")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROGRAM_NOT_FOUND"
