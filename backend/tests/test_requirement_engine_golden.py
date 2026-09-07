from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from backend.scripts.evaluate_requirement_engine import evaluate_cases, load_cases


GOLDEN = Path(__file__).parent / "golden" / "requirement_engine_v1.jsonl"


def test_gold_set_has_required_size_coverage_and_consistency() -> None:
    cases = load_cases(GOLDEN)
    report = evaluate_cases(cases)
    assert report["total"] == 150
    assert set(report["status_counts"]) == {
        "met",
        "unmet",
        "missing_information",
        "manual_review",
        "not_applicable",
    }
    assert min(report["status_counts"].values()) >= 20
    assert min(report["category_counts"].values()) >= 10
    assert min(report["structure_counts"].values()) >= 10
    assert report["overall_accuracy"] == 1.0
    assert report["false_met_rate"] == 0.0
    assert report["explicit_unmet_to_met"] == 0
    assert report["failures"] == []


def test_gold_set_is_fully_independently_reviewed() -> None:
    cases = load_cases(GOLDEN)
    report = evaluate_cases(cases)
    assert report["reviewed"] == report["total"] == 150
    assert report["independent_review_complete"] is True
    assert {case["gold_set_version"] for case in cases} == {
        "requirement_engine_gold.v0.1.0"
    }
    assert {case["review_status"] for case in cases} == {"approved"}
    assert {case["reviewer_role"] for case in cases} == {
        "product_owner_domain_reviewer"
    }
    assert {case["review_date"] for case in cases} == {"2026-09-01"}


def test_formal_metric_command_accepts_reviewed_gold() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.scripts.evaluate_requirement_engine",
            "--golden",
            str(GOLDEN),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0
    assert '"independent_review_complete": true' in result.stdout


def test_consistency_flag_does_not_change_formal_review_status() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.scripts.evaluate_requirement_engine",
            "--golden",
            str(GOLDEN),
            "--allow-pending-review",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0
    assert '"independent_review_complete": true' in result.stdout
