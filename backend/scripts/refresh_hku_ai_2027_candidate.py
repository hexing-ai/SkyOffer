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
PACK_PATH = DATA_ROOT / "programs" / "hk_hku_msc_artificial_intelligence_2027_v1.json"
MANIFEST_PATH = DATA_ROOT / "internal_manifest.json"
SCOPE_PATH = DATA_ROOT / "scope_snapshot.json"

PROGRAM_REF = "program.hk.hku.msc_artificial_intelligence"
PACK_REF = "pack.hk.hku.msc_artificial_intelligence.2027.v1"
VERSION_ID = "version.hku.mscai.2027.refresh.v1"
ADMISSIONS_ID = "evidence.hku.mscai.admissions.2027.v1"
POLICY_ID = "evidence.hku.tpg.requirements.2027.v1"
SOURCE_IDS = [ADMISSIONS_ID, POLICY_ID]

ADMISSIONS_EXCERPT = """Master of Science in Artificial Intelligence
Application for 2027-28 intake opens on September 21, 2026.
Applicants shall hold a Bachelor’s degree or an equivalent qualification.
Applicants should possess knowledge of linear algebra, calculus, probability theory, introductory statistics, and computer programming.
Applicants shall fulfil the University Entrance Requirements.
Round 1 (Main): 12:00 noon (GMT +8), November 16, 2026
Candidates who apply within this period will have priority for admission.
Round 2 (Clearing): 12:00 noon (GMT +8), February 1, 2027"""

POLICY_EXCERPT = """University Entrance Requirements
To be eligible for admission to the courses leading to a taught postgraduate qualification, a candidate shall hold a Bachelor's degree of this University or a qualification of equivalent standard from this University or another comparable institution accepted for this purpose.
English Language Requirements
An applicant whose qualification is from a university or comparable institution outside Hong Kong of which the language of teaching and/or examination is not English is required to obtain one of the listed examination results.
IELTS (International English Language Testing System): A minimum overall band of 6 with no subtest lower than 5.5.
Starting from the 2026 intake, IELTS and TOEFL tests must be taken within two years prior to September 1 of each admissions year."""


def _hash_excerpt(excerpt: str) -> str:
    return hashlib.sha256(excerpt.strip().encode("utf-8")).hexdigest()


def _evidence() -> list[dict]:
    common = {
        "schema_version": "source_evidence.v2",
        "program_id": PROGRAM_REF,
        "applicable_academic_year": "2027-28",
        "availability_at_verification": "available",
        "capture_method": "automated_web_candidate",
        "captured_at": "2026-09-04T07:50:00Z",
        "verified_at": "2026-09-04T07:55:00Z",
        "verified_by": "actor.data_preparer.codex",
        "review_due_at": "2026-09-21T00:00:00Z",
        "expires_at": "2026-12-20T00:00:00Z",
        "hash_scope": "normalized_excerpt",
    }
    return [
        {
            **common,
            "id": ADMISSIONS_ID,
            "source_type": "official_program_page",
            "url": "https://www.mscai.hku.hk/admissions/",
            "official_domain": "www.mscai.hku.hk",
            "page_title": "Admissions - Master of Science in Artificial Intelligence - HKU",
            "excerpt": ADMISSIONS_EXCERPT,
            "snapshot_sha256": _hash_excerpt(ADMISSIONS_EXCERPT),
            "source_version": "2027/28 admissions page verified 2026-09-04",
            "reviewed_source_role": "program",
        },
        {
            **common,
            "id": POLICY_ID,
            "source_type": "official_policy_page",
            "url": "https://portal.hku.hk/tpg-admissions/applying/admission-requirements",
            "official_domain": "portal.hku.hk",
            "page_title": "Admission Requirements | HKU Taught Postgraduate Admissions",
            "excerpt": POLICY_EXCERPT,
            "snapshot_sha256": _hash_excerpt(POLICY_EXCERPT),
            "source_version": "Continuous HKU TPG policy linked by 2027/28 programme page; verified 2026-09-04",
            "reviewed_source_role": "language_policy",
        },
    ]


def _links(source_ids: list[str], support_scope: str) -> list[dict]:
    return [
        {
            "evidence_id": source_id,
            "support_scope": support_scope,
            "citation_order": index,
        }
        for index, source_id in enumerate(source_ids, start=1)
    ]


def _catalog_field(
    field_key: str,
    display_text: str,
    value: dict,
    source_ids: list[str],
) -> dict:
    return {
        "field_key": field_key,
        "value_schema_version": "program_catalog_field.v1",
        "value_payload": {
            "schema_version": "program_catalog_field.v1",
            "field_key": field_key,
            "applicable_academic_year": "2027-28",
            "coverage_status": "confirmed",
            "value": value,
            "reviewed_source_ids": source_ids,
            "review_note": None,
            "reason": None,
        },
        "display_text": display_text,
        "is_critical": field_key in {"catalog.academic_year", "catalog.degree_type"},
        "evidence_links": _links(source_ids, "direct"),
    }


def _requirement_field(
    field_key: str,
    display_text: str,
    requirement_type: str,
    rule: dict,
    source_ids: list[str],
    review_note: str | None = None,
) -> dict:
    digest = hashlib.sha256(field_key.encode("utf-8")).hexdigest()[:10]
    return {
        "field_key": field_key,
        "value_schema_version": "program_requirement_field.v2",
        "value_payload": {
            "schema_version": "program_requirement_field.v2",
            "field_key": field_key,
            "applicable_academic_year": "2027-28",
            "coverage_status": "confirmed",
            "requirements": [
                {
                    "requirement_id": f"requirement.hku.mscai.2027.{digest}",
                    "requirement_type": requirement_type,
                    "is_hard": True,
                    "rule": rule,
                    "evidence_fixture_ids": source_ids,
                    "display_text": display_text,
                }
            ],
            "reviewed_source_ids": source_ids,
            "review_note": review_note,
            "reason": None,
        },
        "display_text": display_text,
        "is_critical": True,
        "evidence_links": _links(source_ids, "direct"),
    }


def _not_found(field: dict) -> dict:
    field_key = field["field_key"]
    note = "本次已核验的 2027/28 项目招生页与 HKU 通用入学要求页未找到该项明确门槛；这不代表学校没有要求。"
    payload = {
        "schema_version": field["value_schema_version"],
        "field_key": field_key,
        "applicable_academic_year": "2027-28",
        "coverage_status": "not_found_in_reviewed_sources",
        "reviewed_source_ids": SOURCE_IDS,
        "review_note": note,
        "reason": {"reason_code": "OFFICIAL_RULE_NOT_FOUND", "detail": note},
    }
    if field["value_schema_version"] == "program_requirement_field.v2":
        payload["requirements"] = []
    else:
        payload["value"] = None
    return {
        **field,
        "display_text": note,
        "value_payload": payload,
        "evidence_links": _links(SOURCE_IDS, "coverage"),
    }


def _build_pack(raw: dict, scope: AlphaScopeSnapshotV1) -> AlphaProgramPackV1:
    admission_only = [ADMISSIONS_ID]
    policy_only = [POLICY_ID]
    existing = {field["field_key"]: field for field in raw["candidate"]["fields"]}

    existing["catalog.academic_year"] = _catalog_field(
        "catalog.academic_year",
        "Application for 2027-28 intake opens on September 21, 2026.",
        {"academic_year": "2027-28"},
        admission_only,
    )
    existing["catalog.application_status"] = _catalog_field(
        "catalog.application_status",
        "Application for 2027-28 intake opens on September 21, 2026.",
        {
            "status": "not_yet_open",
            "opens_on": "2026-09-21",
            "closes_on": "2027-02-01",
        },
        admission_only,
    )
    existing["catalog.degree_type"] = _catalog_field(
        "catalog.degree_type",
        "Master of Science in Artificial Intelligence",
        {"degree_type": "taught_masters"},
        admission_only,
    )
    existing["requirements.degree"] = _requirement_field(
        "requirements.degree",
        "Applicants shall hold a Bachelor’s degree or an equivalent qualification.",
        "degree",
        {
            "node_id": "node.hku.mscai.degree.any",
            "operator": "any",
            "children": [
                {
                    "node_id": "node.hku.mscai.degree.bachelor",
                    "operator": "enum_in",
                    "fact_path": "degree_level",
                    "allowed_values": ["bachelor"],
                },
                {
                    "node_id": "node.hku.mscai.degree.equivalent",
                    "operator": "manual_review",
                    "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                },
            ],
        },
        admission_only,
        "等同学历是否符合要求仍须由学校个案判断。",
    )
    existing["requirements.prerequisite_courses"] = _requirement_field(
        "requirements.prerequisite_courses",
        "Applicants should possess knowledge of linear algebra, calculus, probability theory, introductory statistics, and computer programming.",
        "course",
        {
            "node_id": "node.hku.mscai.courses.all",
            "operator": "all",
            "children": [
                {
                    "node_id": "node.hku.mscai.courses.mathematics",
                    "operator": "course_group",
                    "accepted_tags": ["mathematics"],
                    "minimum_courses": 1,
                },
                {
                    "node_id": "node.hku.mscai.courses.statistics",
                    "operator": "course_group",
                    "accepted_tags": ["statistics"],
                    "minimum_courses": 1,
                },
                {
                    "node_id": "node.hku.mscai.courses.programming",
                    "operator": "course_group",
                    "accepted_tags": ["programming"],
                    "minimum_courses": 1,
                },
                {
                    "node_id": "node.hku.mscai.courses.exact_coverage",
                    "operator": "manual_review",
                    "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                },
            ],
        },
        admission_only,
        "受控课程标签只能初筛数学、统计与编程；线性代数、微积分、概率论和初级统计的精确覆盖仍须核对成绩单。",
    )
    existing["requirements.language"] = _requirement_field(
        "requirements.language",
        "IELTS (International English Language Testing System): A minimum overall band of 6 with no subtest lower than 5.5.",
        "language",
        {
            "node_id": "node.hku.mscai.language.any",
            "operator": "any",
            "children": [
                {
                    "node_id": "node.hku.mscai.language.ielts",
                    "operator": "language_minimum",
                    "test_type": "ielts",
                    "total_min": "6.0",
                    "component_mins": {
                        "listening": "5.5",
                        "reading": "5.5",
                        "writing": "5.5",
                        "speaking": "5.5",
                    },
                },
                {
                    "node_id": "node.hku.mscai.language.other_routes",
                    "operator": "manual_review",
                    "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                },
            ],
        },
        policy_only,
        "英文授课资格、其他考试路径和豁免条件需个案核验。",
    )

    for key in (
        "catalog.department",
        "catalog.duration",
        "catalog.intake",
        "requirements.academic",
        "requirements.materials",
        "requirements.subject",
        "requirements.work_experience",
    ):
        existing[key] = _not_found(existing[key])

    for key in ("taxonomy.primary_direction", "taxonomy.secondary_directions"):
        field = existing[key]
        field["value_payload"]["reviewed_source_ids"] = admission_only
        field["evidence_links"] = _links(admission_only, "direct")

    raw["reviewed_source_ids"] = SOURCE_IDS
    raw["evidence"] = _evidence()
    raw["candidate"]["fields"] = list(existing.values())
    raw["candidate"]["creation_note"] = (
        "HKU MSc Artificial Intelligence 2027/28 官网更新批次；固化学位、先修知识、"
        "语言及申请时间，未见明确门槛继续保留待核验。"
    )
    raw["candidate"]["request_id"] = "request.hku.mscai.2027.refresh.v1"
    raw["review"] = {
        "prepared_by": "actor.data_preparer.codex",
        "prepared_at": "2026-09-04T07:55:00Z",
        "reviewed_by": "actor.domain_reviewer.product_owner",
        "reviewed_at": "2026-09-04T08:00:00Z",
        "review_note": (
            "产品负责人已批准整批审核并接入 HKU AI 2027/28 门槛；官网明确字段进入"
            "Candidate-only，未明确字段继续待核验。"
        ),
        "review_status": "approved",
    }
    raw["expected_semantic_content_sha256"] = "0" * 64
    raw["pack_canonical_sha256"] = "0" * 64
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["expected_semantic_content_sha256"] = alpha_program_pack_semantic_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["pack_canonical_sha256"] = alpha_program_pack_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    validate_alpha_program_pack(pack=pack, scope=scope)
    return pack


def main() -> int:
    scope = AlphaScopeSnapshotV1.model_validate_json(SCOPE_PATH.read_text(encoding="utf-8"))
    pack = _build_pack(json.loads(PACK_PATH.read_text(encoding="utf-8")), scope)
    pack_content = json.dumps(
        pack.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    PACK_PATH.write_text(pack_content, encoding="utf-8")

    raw_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw_manifest["dataset_id"] = "dataset.internal_alpha.2027.v3"
    raw_manifest["created_at"] = "2026-09-04T08:00:00Z"
    entry = next(
        item for item in raw_manifest["programs"] if item["pack_ref"] == PACK_REF
    )
    entry.update(
        {
            "pack_file_sha256": hashlib.sha256(pack_content.encode("utf-8")).hexdigest(),
            "pack_canonical_sha256": pack.pack_canonical_sha256,
            "candidate_semantic_sha256": pack.expected_semantic_content_sha256,
            "candidate_version_id": VERSION_ID,
        }
    )
    raw_manifest["manifest_sha256"] = "0" * 64
    manifest = InternalAlphaManifestV1.model_validate(raw_manifest)
    raw_manifest["manifest_sha256"] = internal_alpha_manifest_hash(manifest)
    manifest = InternalAlphaManifestV1.model_validate(raw_manifest)
    MANIFEST_PATH.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "valid": True,
                "dataset_id": manifest.dataset_id,
                "candidate_version_id": VERSION_ID,
                "evidence_count": len(pack.evidence),
                "confirmed_fields": sum(
                    getattr(field.value_payload, "coverage_status", None) == "confirmed"
                    for field in pack.candidate.fields
                ),
                "pack_canonical_sha256": pack.pack_canonical_sha256,
                "manifest_sha256": manifest.manifest_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
