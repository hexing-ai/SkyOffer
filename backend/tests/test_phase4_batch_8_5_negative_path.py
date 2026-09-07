from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
PROGRAM_DIR = DATA_DIR / "programs"
MATRIX_PATH = DATA_DIR / "sources" / "alpha_program_candidate_matrix_2027_v1.json"
BLOCKED_PROGRAMS = (
    {
        "program_ref": "program.uk.imperial.msc_advanced_aeronautical_engineering",
        "pack_filename": (
            "imperial_msc_advanced_aeronautical_engineering_2027_v1.json"
        ),
        "official_url": (
            "https://www.imperial.ac.uk/study/courses/postgraduate-taught/"
            "advanced-aeronautical-engineering/"
        ),
        "primary_direction": "aerospace_engineering",
        "secondary_directions": [],
        "risk_flags": ["target_year_page_pending"],
    },
    {
        "program_ref": "program.uk.ucl.msc_computer_science",
        "pack_filename": "ucl_msc_computer_science_2027_v1.json",
        "official_url": (
            "https://www.ucl.ac.uk/prospective-students/graduate/"
            "taught-degrees/computer-science-msc"
        ),
        "primary_direction": "computer_science",
        "secondary_directions": [],
        "risk_flags": ["target_year_page_pending"],
    },
    {
        "program_ref": "program.uk.ucl.msc_robotics_artificial_intelligence",
        "pack_filename": (
            "ucl_msc_robotics_artificial_intelligence_2027_v1.json"
        ),
        "official_url": (
            "https://www.ucl.ac.uk/prospective-students/graduate/"
            "taught-degrees/robotics-and-artificial-intelligence-msc"
        ),
        "primary_direction": "low_altitude_economy",
        "secondary_directions": ["artificial_intelligence"],
        "risk_flags": [
            "target_year_page_pending",
            "low_altitude_curriculum_gate_high_risk",
        ],
    },
)


def test_batch_8_5_classified_projects_stay_blocked_without_pack_output() -> None:
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
        assert entry["identity_verification_status"] == "official_page_title_confirmed"
        assert entry["target_year_status"] == "current_official_page_2027_not_explicit"
        assert entry["primary_direction"] == expected["primary_direction"]
        assert entry["secondary_directions"] == expected["secondary_directions"]
        assert entry["risk_flags"] == expected["risk_flags"]


def test_batch_8_5_keeps_manifest_empty_and_non_publishable() -> None:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["template_state"] == "empty_unreviewed"
    assert manifest["publishable"] is False
    assert manifest["programs"] == []
    assert manifest["manifest_sha256"] is None
