from __future__ import annotations

import json
from pathlib import Path

from backend.app.rules.canonical import content_hash
from backend.scripts.audit_coverage_candidate_batch import audit_candidate_batch
from backend.scripts.generate_coverage_candidate_batch import build_batch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
BATCH_PATH = DATA_ROOT / "candidate_batches" / "coverage_2027_batch_v1.json"
QUALITY_PATH = (
    DATA_ROOT / "candidate_batches" / "coverage_2027_batch_v1.quality.json"
)


def test_coverage_candidate_batch_is_deterministic_and_quality_gated():
    stored = json.loads(BATCH_PATH.read_text(encoding="utf-8"))
    generated = build_batch()
    report = audit_candidate_batch(batch_path=BATCH_PATH)

    assert generated == stored
    assert stored["candidate_addition_count"] == 14
    assert stored["projected_internal_program_count"] == 20
    assert stored["public_publishable"] is False
    assert stored["lifecycle_state"].endswith("pending_batch_domain_review")
    assert report["ready_for_batch_domain_review"] is True
    assert report["ready_for_internal_release"] is False
    assert report["issues"] == []
    assert all(report["gates"].values())
    assert report == json.loads(QUALITY_PATH.read_text(encoding="utf-8"))


def test_candidate_batch_never_promotes_older_cycle_admissions_facts():
    batch = json.loads(BATCH_PATH.read_text(encoding="utf-8"))
    allowed_confirmed = {
        "catalog.degree_type",
        "taxonomy.primary_direction",
        "taxonomy.secondary_directions",
        "taxonomy.low_altitude_basis",
    }

    for candidate in batch["candidates"]:
        assert candidate["target_year_status"] == "official_2027_28_rules_pending"
        for field in candidate["field_proposals"]:
            if field["proposed_coverage_status"] == "confirmed":
                assert field["field_key"] in allowed_confirmed
            else:
                assert field["proposed_value"] is None
                assert field["reason_code"] == "OFFICIAL_RULE_NOT_PUBLISHED"


def test_candidate_batch_hash_tampering_fails_closed(tmp_path):
    batch = json.loads(BATCH_PATH.read_text(encoding="utf-8"))
    batch["candidates"][0]["official_name"] = "Tampered"
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(batch), encoding="utf-8")

    report = audit_candidate_batch(batch_path=tampered_path)

    assert report["ready_for_batch_domain_review"] is False
    assert report["gates"]["batch_integrity"] is False
    assert "batch canonical hash mismatch" in report["issues"]


def test_candidate_batch_replacements_are_explicit_and_versioned():
    batch = json.loads(BATCH_PATH.read_text(encoding="utf-8"))
    removed = {item["removed_program_ref"] for item in batch["replacement_diff"]}
    added = {item["added_program_ref"] for item in batch["replacement_diff"]}
    candidate_refs = {item["program_ref"] for item in batch["candidates"]}

    assert removed == {
        "program.uk.manchester.msc_advanced_control_systems_engineering",
        "program.uk.bristol.msc_aerial_robotics",
    }
    assert added == {
        "program.uk.bristol.msc_artificial_intelligence",
        "program.uk.sheffield.msc_advanced_computer_science",
    }
    assert added.issubset(candidate_refs)
    assert removed.isdisjoint(candidate_refs)
    assert batch["batch_canonical_sha256"] == content_hash(
        {
            key: value
            for key, value in batch.items()
            if key != "batch_canonical_sha256"
        }
    )
