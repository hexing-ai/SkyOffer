from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
PROGRAM_DIR = DATA_DIR / "programs"
MATRIX_PATH = DATA_DIR / "sources" / "alpha_program_candidate_matrix_2027_v1.json"
BLOCKED_PROGRAMS = (
    {
        "program_ref": "program.hk.cuhk.msc_computer_science",
        "pack_filename": "cuhk_msc_computer_science_2027_v1.json",
        "official_url": "https://www.cse.cuhk.edu.hk/academics/msc-in-computer-science/",
    },
    {
        "program_ref": (
            "program.hk.polyu.msc_artificial_intelligence_big_data_computing"
        ),
        "pack_filename": (
            "polyu_msc_artificial_intelligence_big_data_computing_2027_v1.json"
        ),
        "official_url": (
            "https://www.polyu.edu.hk/comp/study/taught-postgraduate-programmes/"
            "msc-in-artificial-intelligence-and-big-data-computing/"
        ),
    },
    {
        "program_ref": "program.hk.polyu.msc_information_technology",
        "pack_filename": "polyu_msc_information_technology_2027_v1.json",
        "official_url": (
            "https://www.polyu.edu.hk/comp/study/taught-postgraduate-programmes/"
            "msc-in-information-technology/"
        ),
    },
)


def test_batch_8_3_blocked_projects_stay_in_matrix_without_pack_output() -> None:
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
        assert (
            entry["identity_verification_status"]
            == "official_url_candidate_pending_page_confirmation"
        )
        assert entry["target_year_status"] == "pending_official_confirmation"


def test_batch_8_3_keeps_manifest_empty_and_non_publishable() -> None:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["template_state"] == "empty_unreviewed"
    assert manifest["publishable"] is False
    assert manifest["programs"] == []
    assert manifest["manifest_sha256"] is None
