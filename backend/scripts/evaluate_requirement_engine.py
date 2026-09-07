from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from backend.app.rules.evaluator import RequirementEngine
from backend.app.schemas.requirement_rules import (
    ApplicantEligibilityInput,
    RequirementRuleSet,
)


DEFAULT_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "golden"
    / "requirement_engine_v1.jsonl"
)


def load_cases(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate_cases(cases: list[dict]) -> dict:
    engine = RequirementEngine()
    confusion: dict[str, Counter] = defaultdict(Counter)
    failures: list[dict] = []
    status_counts = Counter()
    categories = Counter()
    structures = Counter()
    reviewed = 0
    false_met = 0
    explicit_unmet_to_met = 0
    non_met = 0
    reason_matches = 0

    for case in cases:
        profile = ApplicantEligibilityInput.model_validate(case["profile"])
        rule_set = RequirementRuleSet.model_validate(case["rule_set"])
        evaluation = engine.evaluate(profile, rule_set)
        actual = evaluation.overall_hard_requirement_status.value
        expected = case["expected_status"]
        actual_reason = evaluation.requirement_results[0].reason_code
        confusion[expected][actual] += 1
        status_counts[expected] += 1
        categories[case["category"]] += 1
        structures[case["structure"]] += 1
        if case.get("review_status") == "approved":
            reviewed += 1
        if expected != "met":
            non_met += 1
            if actual == "met":
                false_met += 1
        if expected == "unmet" and actual == "met":
            explicit_unmet_to_met += 1
        if actual_reason == case["expected_reason_code"]:
            reason_matches += 1
        if actual != expected or actual_reason != case["expected_reason_code"]:
            failures.append(
                {
                    "case_id": case["case_id"],
                    "expected": expected,
                    "actual": actual,
                    "expected_reason": case["expected_reason_code"],
                    "actual_reason": actual_reason,
                }
            )

    total = len(cases)
    correct = sum(confusion[state][state] for state in confusion)
    return {
        "total": total,
        "reviewed": reviewed,
        "independent_review_complete": total > 0 and reviewed == total,
        "overall_accuracy": correct / total if total else None,
        "reason_accuracy": reason_matches / total if total else None,
        "false_met_rate": false_met / non_met if non_met else None,
        "explicit_unmet_to_met": explicit_unmet_to_met,
        "status_counts": dict(sorted(status_counts.items())),
        "category_counts": dict(sorted(categories.items())),
        "structure_counts": dict(sorted(structures.items())),
        "confusion_matrix": {
            expected: dict(sorted(actuals.items()))
            for expected, actuals in sorted(confusion.items())
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument(
        "--allow-pending-review",
        action="store_true",
        help="Allow consistency checks for an explicitly supplied pending-review candidate file.",
    )
    args = parser.parse_args()
    cases = load_cases(args.golden)
    report = evaluate_cases(cases)
    report["golden_path"] = str(args.golden)
    report["golden_sha256"] = hashlib.sha256(args.golden.read_bytes()).hexdigest()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["failures"]:
        return 1
    if not report["independent_review_complete"] and not args.allow_pending_review:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
