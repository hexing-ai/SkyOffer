from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from backend.app.rules.canonical import content_hash
from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.evidence import belongs_to_official_domains
from backend.app.schemas.field_registry import load_program_field_registry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
DEFAULT_BATCH = DATA_ROOT / "candidate_batches" / "coverage_2027_batch_v1.json"
DEFAULT_REPORT = (
    DATA_ROOT / "candidate_batches" / "coverage_2027_batch_v1.quality.json"
)
BASE_DATASET_ID = "dataset.internal_alpha.2027.v1"
BASE_MANIFEST_SHA256 = "b10c4f43c1242864415d720d4dbe1db728a9d240a996df4d60f72bb3ed584938"
BASE_PROGRAM_COUNT = 6


class CandidateBatchAuditError(ValueError):
    pass


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateBatchAuditError(f"cannot load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CandidateBatchAuditError(f"JSON root must be an object: {path}")
    return value


def audit_candidate_batch(
    *, batch_path: Path = DEFAULT_BATCH, data_root: Path = DATA_ROOT
) -> dict:
    batch = _load(batch_path)
    manifest = _load(data_root / "internal_manifest.json")
    scope = AlphaScopeSnapshotV1.model_validate(_load(data_root / "scope_snapshot.json"))
    registry = load_program_field_registry()
    issues: list[str] = []

    expected_hash = content_hash(
        {key: value for key, value in batch.items() if key != "batch_canonical_sha256"}
    )
    if batch.get("batch_canonical_sha256") != expected_hash:
        issues.append("batch canonical hash mismatch")
    if batch.get("schema_version") != "internal_alpha_candidate_batch.v1":
        issues.append("unsupported candidate batch schema")
    if batch.get("lifecycle_state") != "auto_quality_gated_pending_batch_domain_review":
        issues.append("candidate batch lifecycle is not review-pending")
    if batch.get("public_publishable") is not False:
        issues.append("candidate batch must not be publicly publishable")
    if batch.get("target_academic_year") != "2027-28":
        issues.append("candidate batch has the wrong target year")
    if batch.get("source_scope_snapshot_id") != scope.snapshot_id:
        issues.append("candidate batch scope snapshot mismatch")
    if batch.get("base_dataset_id") != BASE_DATASET_ID:
        issues.append("candidate batch base dataset mismatch")
    if batch.get("base_manifest_sha256") != BASE_MANIFEST_SHA256:
        issues.append("candidate batch base manifest hash mismatch")
    if batch.get("base_program_count") != BASE_PROGRAM_COUNT:
        issues.append("candidate batch base count mismatch")

    candidates = batch.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
        issues.append("candidates must be a list")
    if batch.get("candidate_addition_count") != len(candidates):
        issues.append("candidate addition count mismatch")
    if batch.get("projected_internal_program_count") != (
        batch.get("base_program_count", 0) + len(candidates)
    ):
        issues.append("projected internal count mismatch")
    if not 20 <= batch.get("projected_internal_program_count", 0) <= 30:
        issues.append("projected internal count must be between 20 and 30")

    institutions = {
        item.institution_ref: item
        for item in [
            *scope.hong_kong_eight.institutions,
            *scope.united_kingdom_qs_top_100.institutions,
        ]
    }
    candidate_program_refs = {
        item.get("program_ref") for item in candidates if isinstance(item, dict)
    }
    base_program_refs = {
        item["program_ref"]
        for item in manifest["programs"]
        if item["program_ref"] not in candidate_program_refs
    }
    if len(base_program_refs) != BASE_PROGRAM_COUNT:
        issues.append("candidate batch base count mismatch")
    required_fields = {
        item.field_key for item in registry.fields if item.presence == "required"
    }
    directions = {
        "computer_science",
        "artificial_intelligence",
        "aerospace_engineering",
        "low_altitude_economy",
    }
    allowed_confirmed = {
        "catalog.degree_type",
        "taxonomy.primary_direction",
        "taxonomy.secondary_directions",
        "taxonomy.low_altitude_basis",
    }
    seen_program_refs: set[str] = set()
    seen_pack_refs: set[str] = set()
    seen_urls: set[str] = set()
    total_fields = 0
    total_sources = 0
    high_risk_count = 0
    exception_count = 0
    region_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()

    for candidate in candidates:
        ref = candidate.get("program_ref", "<missing>")
        pack_ref = candidate.get("pack_ref", "<missing>")
        url = candidate.get("official_url", "")
        if ref in seen_program_refs or ref in base_program_refs:
            issues.append(f"{ref}: duplicate or already in base dataset")
        seen_program_refs.add(ref)
        if pack_ref in seen_pack_refs:
            issues.append(f"{ref}: duplicate pack ref")
        seen_pack_refs.add(pack_ref)
        if url in seen_urls:
            issues.append(f"{ref}: duplicate official URL")
        seen_urls.add(url)

        institution = institutions.get(candidate.get("institution_ref"))
        if institution is None:
            issues.append(f"{ref}: institution is outside the frozen scope")
            continue
        if candidate.get("region") != institution.region.value:
            issues.append(f"{ref}: region does not match scope")
        host = urlsplit(url).hostname or ""
        if not belongs_to_official_domains(
            host,
            registered_domain=institution.registered_official_domain,
            aliases=institution.official_domain_aliases,
        ):
            issues.append(f"{ref}: official URL is outside the registered domains")
        if candidate.get("degree_type") != "taught_masters":
            issues.append(f"{ref}: degree type is not taught_masters")
        if candidate.get("target_year_status") != "official_2027_28_rules_pending":
            issues.append(f"{ref}: target-year status is not fail-closed")
        primary = candidate.get("primary_direction")
        secondary = candidate.get("secondary_directions", [])
        if primary not in directions or any(value not in directions for value in secondary):
            issues.append(f"{ref}: direction is outside the controlled taxonomy")
        if primary in secondary or len(secondary) != len(set(secondary)):
            issues.append(f"{ref}: direction values are duplicated")
        region_counts[candidate.get("region")] += 1
        direction_counts[primary] += 1

        sources = candidate.get("sources", [])
        source_ids = {item.get("source_id") for item in sources}
        if not sources or len(source_ids) != len(sources):
            issues.append(f"{ref}: source set is empty or duplicated")
        for source in sources:
            excerpt = source.get("excerpt", "")
            if source.get("url") != url:
                issues.append(f"{ref}: source URL differs from official program URL")
            if source.get("capture_method") != "automated_web_candidate":
                issues.append(f"{ref}: source is not marked as automated candidate capture")
            if source.get("snapshot_sha256") != hashlib.sha256(
                excerpt.encode("utf-8")
            ).hexdigest():
                issues.append(f"{ref}: source excerpt hash mismatch")
            if not source.get("page_title") or not excerpt:
                issues.append(f"{ref}: source title or excerpt is empty")
        total_sources += len(sources)

        fields = candidate.get("field_proposals", [])
        field_by_key = {item.get("field_key"): item for item in fields}
        expected_fields = set(required_fields)
        low_altitude = "low_altitude_economy" in {primary, *secondary}
        if low_altitude:
            expected_fields.add("taxonomy.low_altitude_basis")
        if set(field_by_key) != expected_fields or len(field_by_key) != len(fields):
            issues.append(f"{ref}: field inventory differs from Registry")
        for field in fields:
            key = field.get("field_key")
            status = field.get("proposed_coverage_status")
            value = field.get("proposed_value")
            if not set(field.get("source_ids", [])).issubset(source_ids):
                issues.append(f"{ref}/{key}: field references unknown sources")
            if status == "confirmed":
                if key not in allowed_confirmed or value is None:
                    issues.append(f"{ref}/{key}: unsafe confirmed field")
            else:
                if value is not None or not field.get("reason_code"):
                    issues.append(f"{ref}/{key}: unresolved field retained a value or lacks reason")
            if key == "catalog.academic_year" and status == "confirmed":
                issues.append(f"{ref}: 2027-28 academic year must remain unresolved")
        total_fields += len(fields)

        expected_high_risk = sorted(
            item["field_key"]
            for item in fields
            if item.get("is_critical") and item.get("proposed_coverage_status") != "confirmed"
        )
        expected_exceptions = sorted(
            item["field_key"]
            for item in fields
            if item.get("proposed_coverage_status") != "confirmed"
        )
        if candidate.get("high_risk_field_keys") != expected_high_risk:
            issues.append(f"{ref}: high-risk disclosure mismatch")
        if candidate.get("exception_field_keys") != expected_exceptions:
            issues.append(f"{ref}: exception disclosure mismatch")
        high_risk_count += len(expected_high_risk)
        exception_count += len(expected_exceptions)

        basis = candidate.get("low_altitude_basis")
        if low_altitude:
            if not basis or not basis.get("courses"):
                issues.append(f"{ref}: low-altitude basis or courses are missing")
            else:
                curriculum_sources = {
                    item["source_id"]: item
                    for item in sources
                    if item.get("reviewed_source_role") == "curriculum"
                }
                courses = basis["courses"]
                if basis.get("inclusion_basis") == "curriculum_based" and (
                    len(courses) < 2
                    or not any(item.get("course_type") in {"core", "required"} for item in courses)
                ):
                    issues.append(f"{ref}: curriculum-based low-altitude gate is incomplete")
                for course in courses:
                    source = curriculum_sources.get(course.get("source_id"))
                    if source is None or course.get("course_name") not in source["excerpt"]:
                        issues.append(f"{ref}: low-altitude course evidence is incomplete")
                    marker = course.get("course_type")
                    accepted_markers = {
                        "core": ("core", "compulsory"),
                        "required": ("required", "compulsory"),
                        "elective": ("elective", "optional"),
                    }
                    if (
                        marker != "unknown"
                        and source is not None
                        and not any(
                            value in source["excerpt"].casefold()
                            for value in accepted_markers.get(marker, ())
                        )
                    ):
                        issues.append(f"{ref}: low-altitude course type is not in excerpt")
        elif basis is not None:
            issues.append(f"{ref}: low-altitude basis exists without the direction")

    report = {
        "schema_version": "internal_alpha_candidate_batch_quality.v1",
        "batch_id": batch.get("batch_id"),
        "batch_canonical_sha256": expected_hash,
        "candidate_addition_count": len(candidates),
        "projected_internal_program_count": batch.get("base_program_count", 0)
        + len(candidates),
        "source_count": total_sources,
        "field_proposal_count": total_fields,
        "high_risk_field_count": high_risk_count,
        "exception_field_count": exception_count,
        "region_counts": dict(sorted(region_counts.items())),
        "primary_direction_counts": dict(sorted(direction_counts.items())),
        "gates": {
            "batch_integrity": not any("batch" in issue for issue in issues),
            "scope_and_domain": not any(
                "scope" in issue or "domain" in issue or "region" in issue
                for issue in issues
            ),
            "unique_identity": not any("duplicate" in issue for issue in issues),
            "field_inventory": not any("field inventory" in issue for issue in issues),
            "source_hashes": not any("source" in issue and "hash" in issue for issue in issues),
            "target_year_fail_closed": not any(
                "target-year" in issue or "academic year" in issue for issue in issues
            ),
            "risk_disclosure": not any(
                "high-risk disclosure" in issue or "exception disclosure" in issue
                for issue in issues
            ),
            "low_altitude_evidence": not any("low-altitude" in issue for issue in issues),
        },
        "ready_for_batch_domain_review": not issues,
        "ready_for_internal_release": False,
        "issues": sorted(set(issues)),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--write-report", type=Path, default=None)
    args = parser.parse_args()
    report = audit_candidate_batch(batch_path=args.batch)
    if args.write_report is not None:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ready_for_batch_domain_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
