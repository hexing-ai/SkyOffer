from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "golden"
    / "requirement_engine_v1.jsonl"
)


def approve_cases(
    path: Path,
    case_ids: set[str],
    *,
    reviewer_role: str,
    review_date: str,
) -> int:
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    available = {case["case_id"] for case in cases}
    missing = sorted(case_ids.difference(available))
    if missing:
        raise ValueError(f"unknown case IDs: {missing}")

    changed = 0
    for case in cases:
        if case["case_id"] not in case_ids:
            continue
        existing_role = case.get("reviewer_role")
        existing_date = case.get("review_date")
        if case.get("review_status") == "approved":
            if existing_role != reviewer_role or existing_date != review_date:
                raise ValueError(f"conflicting prior review: {case['case_id']}")
            continue
        case["review_status"] = "approved"
        case["reviewer_role"] = reviewer_role
        case["review_date"] = review_date
        changed += 1

    body = "\n".join(
        json.dumps(case, ensure_ascii=False, sort_keys=True) for case in cases
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(body + "\n", encoding="utf-8")
    temporary.replace(path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--case-prefix", action="append", default=[])
    parser.add_argument("--expected-count", type=int)
    parser.add_argument(
        "--reviewer-role", default="product_owner_domain_reviewer"
    )
    parser.add_argument("--review-date", required=True)
    args = parser.parse_args()
    available_cases = [
        json.loads(line)
        for line in args.golden.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    case_ids = set(args.case_id)
    for prefix in args.case_prefix:
        case_ids.update(
            case["case_id"]
            for case in available_cases
            if case["case_id"].startswith(prefix)
        )
    if not case_ids:
        parser.error("at least one --case-id or --case-prefix is required")
    if args.expected_count is not None and len(case_ids) != args.expected_count:
        parser.error(
            f"resolved {len(case_ids)} cases, expected {args.expected_count}"
        )
    changed = approve_cases(
        args.golden,
        case_ids,
        reviewer_role=args.reviewer_role,
        review_date=args.review_date,
    )
    print(f"recorded {changed} new approvals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
