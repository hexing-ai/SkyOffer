from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.app.schemas.alpha_manifest import AlphaScopeSnapshotV1
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.internal_alpha import InternalAlphaManifestV1
from backend.app.services.alpha_program_pack_validator import (
    alpha_program_pack_hash,
    alpha_program_pack_semantic_hash,
    validate_alpha_program_pack,
)
from backend.app.services.internal_alpha_quality import internal_alpha_manifest_hash


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
BATCH_PATH = DATA_ROOT / "candidate_batches" / "coverage_2027_batch_v1.json"
MANIFEST_PATH = DATA_ROOT / "internal_manifest.json"
PROGRAMS_DIR = DATA_ROOT / "programs"

PREPARED_AT = "2026-09-04T12:30:00+08:00"
REVIEWED_AT = "2026-09-04T13:00:00+08:00"
REVIEW_NOTE = (
    "产品负责人已整批确认 20 项候选批次领域复核通过；本 Pack 仍为 Candidate-only，"
    "未确认的 2027/28 字段继续保持待核验状态。"
)
UNRESOLVED_NOTE = (
    "2027/28 目标周期招生事实尚未在本批官方来源中发布或完成核验；"
    "不沿用 2026/27 数值、日期或门槛。"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _institutions(scope: AlphaScopeSnapshotV1) -> dict[str, object]:
    return {
        item.institution_ref: item
        for item in (
            *scope.hong_kong_eight.institutions,
            *scope.united_kingdom_qs_top_100.institutions,
        )
    }


def _schema_for(field_key: str) -> str:
    if field_key.startswith("catalog."):
        return "program_catalog_field.v1"
    if field_key.startswith("requirements."):
        return "program_requirement_field.v2"
    return "program_taxonomy_field.v1"


def _program_source_id(candidate: dict) -> str:
    return next(
        source["source_id"]
        for source in candidate["sources"]
        if source["reviewed_source_role"] == "program"
    )


def _field(candidate: dict, proposal: dict) -> dict:
    field_key = proposal["field_key"]
    status = proposal["proposed_coverage_status"]
    schema_version = _schema_for(field_key)
    if status == "confirmed" and field_key != "taxonomy.low_altitude_basis":
        source_ids = [_program_source_id(candidate)]
        display_text = candidate["official_name"]
        links = [
            {
                "evidence_id": source_ids[0],
                "support_scope": "direct",
                "citation_order": 1,
            }
        ]
    elif status == "confirmed":
        source_ids = proposal["source_ids"]
        display_text = proposal["proposed_value"]["rationale_zh"]
        links = [
            {
                "evidence_id": source_id,
                "support_scope": "direct",
                "citation_order": index,
            }
            for index, source_id in enumerate(source_ids, start=1)
        ]
    else:
        source_ids = proposal["source_ids"]
        display_text = proposal["review_note"] or UNRESOLVED_NOTE
        links = [
            {
                "evidence_id": source_id,
                "support_scope": "coverage",
                "citation_order": index,
            }
            for index, source_id in enumerate(source_ids, start=1)
        ]

    common = {
        "schema_version": schema_version,
        "field_key": field_key,
        "applicable_academic_year": "2027-28",
        "coverage_status": status,
        "reviewed_source_ids": source_ids,
        "review_note": proposal["review_note"],
        "reason": (
            None
            if status == "confirmed"
            else {
                "reason_code": proposal["reason_code"],
                "detail": display_text,
            }
        ),
    }
    if schema_version == "program_requirement_field.v2":
        payload = {**common, "requirements": []}
    else:
        value = proposal["proposed_value"]
        if field_key == "taxonomy.low_altitude_basis" and value is not None:
            courses = [
                {
                    "course_name": course["course_name"],
                    "course_type": course["course_type"],
                    "subtag": course["subtag"],
                    "evidence_id": course["source_id"],
                }
                for course in value["courses"]
            ]
            value = {
                "inclusion_basis": value["inclusion_basis"],
                "subtags": sorted({course["subtag"] for course in courses}),
                "rationale_zh": value["rationale_zh"],
                "courses": courses,
                "counterexample_check_completed": True,
            }
        payload = {**common, "value": value}
    return {
        "field_key": field_key,
        "value_schema_version": schema_version,
        "value_payload": payload,
        "display_text": display_text,
        "is_critical": proposal["is_critical"],
        "evidence_links": links,
    }


def _pack(candidate: dict, scope: AlphaScopeSnapshotV1) -> AlphaProgramPackV1:
    institution = _institutions(scope)[candidate["institution_ref"]]
    sources = candidate["sources"]
    evidence = [
        {
            "schema_version": "source_evidence.v2",
            "id": source["source_id"],
            "program_id": candidate["program_ref"],
            "source_type": "official_program_page",
            "url": source["url"],
            "official_domain": source["official_domain"],
            "page_title": source["page_title"],
            "excerpt": source["excerpt"],
            "snapshot_sha256": source["snapshot_sha256"],
            "source_version": source["source_version"],
            "captured_at": source["captured_at"],
            "verified_at": PREPARED_AT,
            "verified_by": "actor.data_preparer.codex",
            "review_due_at": source["review_due_at"],
            "expires_at": source["expires_at"],
            "availability_at_verification": "available",
            "capture_method": source["capture_method"],
            "hash_scope": "normalized_excerpt",
            "reviewed_source_role": source["reviewed_source_role"],
            "applicable_academic_year": "2027-28",
        }
        for source in sources
    ]
    raw = {
        "schema_version": "alpha_program_pack.v1",
        "pack_ref": candidate["pack_ref"],
        "scope_snapshot_id": scope.snapshot_id,
        "scope_institution_ref": candidate["institution_ref"],
        "target_academic_year": "2027-28",
        "program": {
            "program_ref": candidate["program_ref"],
            "official_name": candidate["official_name"],
            "institution_name": institution.official_name,
            "region": candidate["region"],
            "official_program_url": candidate["official_url"],
            "registered_official_domain": institution.registered_official_domain,
            "official_domain_aliases": institution.official_domain_aliases,
            "degree_type": "taught_masters",
            "created_by": "actor.data_preparer.codex",
            "creation_note": "20 项内部 Alpha 扩容批次中的 Candidate-only 项目。",
        },
        "reviewed_source_ids": [source["source_id"] for source in sources],
        "evidence": evidence,
        "candidate": {
            "base_version_id": None,
            "fields": [_field(candidate, item) for item in candidate["field_proposals"]],
            "created_by": "actor.data_preparer.codex",
            "creation_note": (
                "20 项内部 Alpha 扩容；仅固化已复核的项目身份、授课型硕士和专业方向，"
                "其余 2027/28 字段保持待核验。"
            ),
            "request_id": f"request.phase5.coverage.{hashlib.sha256(candidate['program_ref'].encode()).hexdigest()[:16]}",
        },
        "review": {
            "prepared_by": "actor.data_preparer.codex",
            "prepared_at": PREPARED_AT,
            "reviewed_by": "actor.domain_reviewer.product_owner",
            "reviewed_at": REVIEWED_AT,
            "review_note": REVIEW_NOTE,
            "review_status": "approved",
        },
        "pack_canonical_sha256": "0" * 64,
        "expected_semantic_content_sha256": "0" * 64,
    }
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["expected_semantic_content_sha256"] = alpha_program_pack_semantic_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["pack_canonical_sha256"] = alpha_program_pack_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    validate_alpha_program_pack(pack=pack, scope=scope)
    return pack


def _write_pack(pack: AlphaProgramPackV1) -> tuple[str, str]:
    name = pack.program.program_ref.split("program.", 1)[1].replace(".", "_") + "_2027_v1.json"
    path = PROGRAMS_DIR / name
    content = json.dumps(
        pack.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    path.write_text(content, encoding="utf-8")
    return f"programs/{name}", hashlib.sha256(content.encode("utf-8")).hexdigest()


def main() -> int:
    batch = _json(BATCH_PATH)
    scope = AlphaScopeSnapshotV1.model_validate(_json(DATA_ROOT / "scope_snapshot.json"))
    old_manifest = InternalAlphaManifestV1.model_validate(_json(MANIFEST_PATH))
    addition_refs = {item["pack_ref"] for item in batch["candidates"]}
    base_entries = [
        item for item in old_manifest.programs if item.pack_ref not in addition_refs
    ]
    if len(base_entries) != batch["base_program_count"]:
        raise RuntimeError("internal manifest does not contain the reviewed six-program base")
    new_entries = []
    for index, candidate in enumerate(batch["candidates"], start=1):
        pack = _pack(candidate, scope)
        pack_path, file_hash = _write_pack(pack)
        new_entries.append(
            {
                "pack_ref": pack.pack_ref,
                "pack_path": pack_path,
                "pack_file_sha256": file_hash,
                "pack_canonical_sha256": pack.pack_canonical_sha256,
                "candidate_semantic_sha256": pack.expected_semantic_content_sha256,
                "program_ref": pack.program.program_ref,
                "candidate_version_id": f"version.phase5.coverage.{index:02d}",
                "institution_ref": pack.scope_institution_ref,
                "region": pack.program.region.value,
            }
        )
    raw_manifest = {
        **old_manifest.model_dump(mode="json", exclude={"manifest_sha256"}),
        "dataset_id": "dataset.internal_alpha.2027.v2",
        "created_at": REVIEWED_AT,
        "program_count": len(base_entries) + len(new_entries),
        "programs": [
            *(item.model_dump(mode="json") for item in base_entries),
            *new_entries,
        ],
        "manifest_sha256": "0" * 64,
    }
    manifest = InternalAlphaManifestV1.model_validate(raw_manifest)
    raw_manifest["manifest_sha256"] = internal_alpha_manifest_hash(manifest)
    manifest = InternalAlphaManifestV1.model_validate(raw_manifest)
    MANIFEST_PATH.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "valid": True,
                "dataset_id": manifest.dataset_id,
                "program_count": manifest.program_count,
                "new_program_count": len(new_entries),
                "manifest_sha256": manifest.manifest_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
