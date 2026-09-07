from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
PROGRAM_DIR = DATA_DIR / "programs"
MATRIX_PATH = DATA_DIR / "sources" / "alpha_program_candidate_matrix_2027_v1.json"
BLOCKED_PROGRAMS = (
    {
        "program_ref": "program.hk.hkbu.msc_ai_digital_media",
        "pack_filename": "hkbu_msc_ai_digital_media_2027_v1.json",
        "official_url": "https://www.comm.hkbu.edu.hk/masters/en/aidm/",
        "identity_status": "official_url_candidate_pending_page_confirmation",
        "target_year_status": "pending_official_confirmation",
    },
    {
        "program_ref": "program.uk.imperial.msc_computing",
        "pack_filename": "imperial_msc_computing_2027_v1.json",
        "official_url": (
            "https://www.imperial.ac.uk/study/courses/postgraduate-taught/"
            "computing/"
        ),
        "identity_status": "official_page_title_confirmed",
        "target_year_status": "current_official_page_2027_not_explicit",
    },
    {
        "program_ref": "program.uk.imperial.msc_artificial_intelligence",
        "pack_filename": "imperial_msc_artificial_intelligence_2027_v1.json",
        "official_url": (
            "https://www.imperial.ac.uk/study/courses/postgraduate-taught/"
            "artificial-intelligence/"
        ),
        "identity_status": "official_page_title_confirmed",
        "target_year_status": "current_official_page_2027_not_explicit",
    },
)


def test_batch_8_4_blocked_projects_stay_in_matrix_without_pack_output() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    actual_files = {path.name for path in PROGRAM_DIR.glob("*.json")}
    entries = {item["program_ref"]: item for item in matrix["programs"]}

    matrix_order = [item["program_ref"] for item in matrix["programs"]]
    expected_order = [item["program_ref"] for item in BLOCKED_PROGRAMS]
    start = matrix_order.index(expected_order[0])
    assert matrix_order[start : start + len(expected_order)] == expected_order

    for expected in BLOCKED_PROGRAMS:
        assert expected["pack_filename"] not in actual_files
        entry = entries[expected["program_ref"]]
        assert entry["official_url"] == expected["official_url"]
        assert entry["identity_verification_status"] == expected["identity_status"]
        assert entry["target_year_status"] == expected["target_year_status"]


def test_batch_8_4_keeps_manifest_empty_and_non_publishable() -> None:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["template_state"] == "empty_unreviewed"
    assert manifest["publishable"] is False
    assert manifest["programs"] == []
    assert manifest["manifest_sha256"] is None
