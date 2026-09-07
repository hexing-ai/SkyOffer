from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.field_registry import load_program_field_registry
from backend.app.services.alpha_program_pack_validator import (
    alpha_program_pack_hash,
    alpha_program_pack_semantic_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "backend" / "data" / "alpha_v1" / "programs"
ACADEMIC_YEAR = "2027-28"
PREPARED_AT = "2026-09-03T15:35:00+08:00"
REVIEWED_AT = "2026-09-03T15:43:00+08:00"
PREPARER = "actor.data_preparer.codex"
REVIEWER = "actor.domain_reviewer.product_owner"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _links(source_ids: list[str], support_scope: str) -> list[dict]:
    return [
        {
            "evidence_id": evidence_id,
            "support_scope": support_scope,
            "citation_order": index,
        }
        for index, evidence_id in enumerate(source_ids, start=1)
    ]


def _reason(code: str, detail: str) -> dict:
    return {"reason_code": code, "detail": detail}


def _catalog_field(
    field_key: str,
    *,
    status: str,
    display_text: str,
    source_ids: list[str],
    value: dict | None = None,
    reason_code: str | None = None,
    review_note: str | None = None,
    support_scope: str = "direct",
) -> dict:
    registry = load_program_field_registry().definition_for(field_key)
    reason = None if reason_code is None else _reason(reason_code, display_text)
    return {
        "field_key": field_key,
        "value_schema_version": "program_catalog_field.v1",
        "value_payload": {
            "schema_version": "program_catalog_field.v1",
            "field_key": field_key,
            "applicable_academic_year": ACADEMIC_YEAR,
            "coverage_status": status,
            "value": value,
            "reviewed_source_ids": source_ids,
            "review_note": review_note or (display_text if status != "confirmed" else None),
            "reason": reason,
        },
        "display_text": display_text,
        "is_critical": registry.is_critical,
        "evidence_links": _links(source_ids, support_scope),
    }


def _taxonomy_field(
    field_key: str,
    *,
    display_text: str,
    source_ids: list[str],
    value: dict,
    review_note: str,
) -> dict:
    registry = load_program_field_registry().definition_for(field_key)
    return {
        "field_key": field_key,
        "value_schema_version": "program_taxonomy_field.v1",
        "value_payload": {
            "schema_version": "program_taxonomy_field.v1",
            "field_key": field_key,
            "applicable_academic_year": ACADEMIC_YEAR,
            "coverage_status": "confirmed",
            "value": value,
            "reviewed_source_ids": source_ids,
            "review_note": review_note,
            "reason": None,
        },
        "display_text": display_text,
        "is_critical": registry.is_critical,
        "evidence_links": _links(source_ids, "direct"),
    }


def _requirement_field(
    field_key: str,
    *,
    status: str,
    display_text: str,
    source_ids: list[str],
    requirements: list[dict] | None = None,
    reason_code: str | None = None,
    support_scope: str = "direct",
) -> dict:
    registry = load_program_field_registry().definition_for(field_key)
    reason = None if reason_code is None else _reason(reason_code, display_text)
    return {
        "field_key": field_key,
        "value_schema_version": "program_requirement_field.v2",
        "value_payload": {
            "schema_version": "program_requirement_field.v2",
            "field_key": field_key,
            "applicable_academic_year": ACADEMIC_YEAR,
            "coverage_status": status,
            "requirements": requirements or [],
            "reviewed_source_ids": source_ids,
            "review_note": None if status == "confirmed" else display_text,
            "reason": reason,
        },
        "display_text": display_text,
        "is_critical": registry.is_critical,
        "evidence_links": _links(source_ids, support_scope),
    }


def _requirement(
    requirement_id: str,
    requirement_type: str,
    display_text: str,
    evidence_ids: list[str],
    rule: dict,
) -> dict:
    return {
        "requirement_id": requirement_id,
        "requirement_type": requirement_type,
        "is_hard": True,
        "applicability": None,
        "rule": rule,
        "evidence_fixture_ids": evidence_ids,
        "display_text": display_text,
    }


def _evidence(
    *,
    evidence_id: str,
    program_id: str,
    url: str,
    official_domain: str,
    page_title: str,
    excerpt: str,
    source_type: str,
    source_version: str,
    role: str,
) -> dict:
    return {
        "schema_version": "source_evidence.v2",
        "applicable_academic_year": ACADEMIC_YEAR,
        "id": evidence_id,
        "program_id": program_id,
        "source_type": source_type,
        "url": url,
        "official_domain": official_domain,
        "page_title": page_title,
        "excerpt": excerpt,
        "snapshot_sha256": _sha256(excerpt),
        "source_version": source_version,
        "captured_at": PREPARED_AT,
        "verified_at": REVIEWED_AT,
        "verified_by": PREPARER,
        "review_due_at": "2026-10-03T15:43:00+08:00",
        "expires_at": "2026-12-02T15:43:00+08:00",
        "availability_at_verification": "available",
        "capture_method": "manual_browser",
        "hash_scope": "normalized_excerpt",
        "reviewed_source_role": role,
    }


def _signed_pack(raw: dict) -> dict:
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["expected_semantic_content_sha256"] = alpha_program_pack_semantic_hash(pack)
    pack = AlphaProgramPackV1.model_validate(raw)
    raw["pack_canonical_sha256"] = alpha_program_pack_hash(pack)
    AlphaProgramPackV1.model_validate(raw)
    # Keep the authored JSON ordering. Pydantic serializes frozenset values through
    # hash-randomized iteration, which would make checked-in Pack bytes drift across
    # Python processes even though both canonical hashes remain stable.
    return raw


def _hku_pack() -> dict:
    program_ref = "program.hk.hku.msc_computer_science"
    evidence_id = "evidence.hku.msccs.program.2027.v1"
    source_ids = [evidence_id]
    excerpt = "\n".join(
        [
            "MSc in Computer Science",
            "School of Computing and Data Science",
            "Taught Master Programmes",
            "Computer Science",
            "The application for 2026/27 intake is now closed. Application for 2027/28 intake will open around October 2026.",
        ]
    )
    evidence = _evidence(
        evidence_id=evidence_id,
        program_id=program_ref,
        url="https://master.cds.hku.hk/msccs/",
        official_domain="master.cds.hku.hk",
        page_title="MSc in Computer Science Home - HKU, School of Computing and Data Science, Taught Master Programmes",
        excerpt=excerpt,
        source_type="official_program_page",
        source_version="2027/28 intake notice manually verified on 2026-09-03",
        role="program",
    )
    not_published = "2027/28 详细规则尚未在本次已核验官网来源中发布，保留人工核验。"
    not_found = "本次已核验的完整官网来源未找到该项 2027/28 明确要求；这不代表学校没有要求。"
    fields = [
        _catalog_field(
            "catalog.academic_year",
            status="confirmed",
            display_text="2027/28",
            source_ids=source_ids,
            value={"academic_year": ACADEMIC_YEAR},
        ),
        _catalog_field(
            "catalog.degree_type",
            status="confirmed",
            display_text="Taught Master Programmes",
            source_ids=source_ids,
            value={"degree_type": "taught_masters"},
        ),
        _catalog_field(
            "catalog.department",
            status="confirmed",
            display_text="School of Computing and Data Science",
            source_ids=source_ids,
            value={"department_name": "School of Computing and Data Science"},
        ),
        _catalog_field(
            "catalog.duration",
            status="manual_review",
            display_text=not_published,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_PUBLISHED",
            support_scope="coverage",
        ),
        _catalog_field(
            "catalog.intake",
            status="not_found_in_reviewed_sources",
            display_text=not_found,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _catalog_field(
            "catalog.application_status",
            status="confirmed",
            display_text="Application for 2027/28 intake will open around October 2026.",
            source_ids=source_ids,
            value={"status": "not_yet_open", "opens_on": None, "closes_on": None},
        ),
        _taxonomy_field(
            "taxonomy.primary_direction",
            display_text="Computer Science",
            source_ids=source_ids,
            value={"direction": "computer_science"},
            review_note="项目名称直接支持计算机科学主方向。",
        ),
        _taxonomy_field(
            "taxonomy.secondary_directions",
            display_text="MSc in Computer Science",
            source_ids=source_ids,
            value={"directions": []},
            review_note="保持已复核候选矩阵口径，不从项目名称推断次方向。",
        ),
        _requirement_field(
            "requirements.degree",
            status="manual_review",
            display_text=not_published,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_PUBLISHED",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.academic",
            status="not_found_in_reviewed_sources",
            display_text=not_found,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.subject",
            status="not_found_in_reviewed_sources",
            display_text=not_found,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.prerequisite_courses",
            status="not_found_in_reviewed_sources",
            display_text=not_found,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.language",
            status="manual_review",
            display_text=not_published,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_PUBLISHED",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.work_experience",
            status="not_found_in_reviewed_sources",
            display_text=not_found,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.materials",
            status="manual_review",
            display_text=not_published,
            source_ids=source_ids,
            reason_code="OFFICIAL_RULE_NOT_PUBLISHED",
            support_scope="coverage",
        ),
    ]
    return _signed_pack(
        {
            "schema_version": "alpha_program_pack.v1",
            "pack_ref": "pack.hk.hku.msc_computer_science.2027.v1",
            "scope_snapshot_id": "scope.alpha.2027.v2",
            "scope_institution_ref": "institution.hk.hku",
            "target_academic_year": ACADEMIC_YEAR,
            "program": {
                "program_ref": program_ref,
                "official_name": "MSc in Computer Science",
                "institution_name": "The University of Hong Kong",
                "region": "hong_kong",
                "official_program_url": "https://master.cds.hku.hk/msccs/",
                "registered_official_domain": "hku.hk",
                "official_domain_aliases": [],
                "degree_type": "taught_masters",
                "created_by": PREPARER,
                "creation_note": "第四阶段 8.1 首组，经三页官网人工核验后生成的 HKU Candidate-only Program。",
            },
            "reviewed_source_ids": source_ids,
            "evidence": [evidence],
            "candidate": {
                "base_version_id": None,
                "fields": fields,
                "created_by": PREPARER,
                "creation_note": "第四阶段 8.1 HKU 首组候选；未确认字段全部 fail closed。",
                "request_id": "request.phase4.batch8.1.hku.msccs.v1",
            },
            "review": {
                "prepared_by": PREPARER,
                "prepared_at": PREPARED_AT,
                "reviewed_by": REVIEWER,
                "reviewed_at": REVIEWED_AT,
                "review_note": "产品负责人确认 HKU 项目主页手工核验通过；仅按冻结字段口径生成 Candidate Pack。",
                "review_status": "approved",
            },
            "pack_canonical_sha256": "0" * 64,
            "expected_semantic_content_sha256": "0" * 64,
        }
    )


def _hkust_pack() -> dict:
    program_ref = "program.hk.hkust.msc_aeronautical_engineering"
    program_evidence_id = "evidence.hkust.mscae.program.2027.v1"
    catalog_evidence_id = "evidence.hkust.mscae.catalog.2027.v1"
    all_source_ids = [catalog_evidence_id, program_evidence_id]
    program_excerpt = "\n".join(
        [
            "MSc in Aeronautical Engineering",
            "Fresh graduates who have good academic record are also our targets.",
            "For 2027/28 Fall intake (September 2027):",
            "All applications are considered on a competitive and rolling basis.",
        ]
    )
    catalog_excerpt = "\n".join(
        [
            "Postgraduate Programs 2027/28",
            "Master of Science Program in Aeronautical Engineering",
            "Master of Science in Aeronautical Engineering",
            "Both full- and part-time",
            "Full-time: 1 year",
            "Part-time: 2 years",
            "Department of Mechanical and Aerospace Engineering",
            "For 2027/28 Fall Term Intake (commencing in Sep 2027):",
            "Admissions is on rolling basis.",
            "A bachelor’s degree in Engineering, Science or related areas, with second class honors or above.",
            "IELTS (Academic Module): Overall score: 6.5 and All sub-score: 5.5 *",
        ]
    )
    program_evidence = _evidence(
        evidence_id=program_evidence_id,
        program_id=program_ref,
        url="https://seng.hkust.edu.hk/academics/taught-postgraduate/msc-ae",
        official_domain="seng.hkust.edu.hk",
        page_title="MSc in Aeronautical Engineering | HKUST School of Engineering",
        excerpt=program_excerpt,
        source_type="official_program_page",
        source_version="2027/28 Fall intake page manually verified on 2026-09-03",
        role="program",
    )
    catalog_evidence = _evidence(
        evidence_id=catalog_evidence_id,
        program_id=program_ref,
        url="https://prog-crs.hkust.edu.hk/pgprog/2027-28/msc-ae",
        official_domain="prog-crs.hkust.edu.hk",
        page_title="Program & Course Catalog",
        excerpt=catalog_excerpt,
        source_type="official_policy_page",
        source_version="Postgraduate Programs 2027/28 manually verified on 2026-09-03",
        role="admissions_policy",
    )
    catalog_only = [catalog_evidence_id]
    program_only = [program_evidence_id]
    degree_display = "A bachelor’s degree in Engineering, Science or related areas, with second class honors or above."
    language_display = "IELTS (Academic Module): Overall score: 6.5 and All sub-score: 5.5 *"
    fields = [
        _catalog_field(
            "catalog.academic_year",
            status="confirmed",
            display_text="Postgraduate Programs 2027/28",
            source_ids=catalog_only,
            value={"academic_year": ACADEMIC_YEAR},
        ),
        _catalog_field(
            "catalog.degree_type",
            status="confirmed",
            display_text="Master of Science in Aeronautical Engineering",
            source_ids=catalog_only,
            value={"degree_type": "taught_masters"},
        ),
        _catalog_field(
            "catalog.department",
            status="confirmed",
            display_text="Department of Mechanical and Aerospace Engineering",
            source_ids=catalog_only,
            value={"department_name": "Department of Mechanical and Aerospace Engineering"},
        ),
        _catalog_field(
            "catalog.duration",
            status="confirmed",
            display_text="Full-time: 1 year",
            source_ids=catalog_only,
            value={"months": 12, "study_mode": "mixed"},
            review_note="同页同时确认 full-time 1 year 与 part-time 2 years；结构化主时长按全日制 12 个月，模式记 mixed。",
        ),
        _catalog_field(
            "catalog.intake",
            status="confirmed",
            display_text="September 2027",
            source_ids=program_only,
            value={"intake_months": [9]},
        ),
        _catalog_field(
            "catalog.application_status",
            status="confirmed",
            display_text="Admissions is on rolling basis.",
            source_ids=all_source_ids,
            value={"status": "rolling", "opens_on": None, "closes_on": None},
            review_note="两页均确认 rolling；因第三轮日期冲突，不写单一 closes_on。",
        ),
        _taxonomy_field(
            "taxonomy.primary_direction",
            display_text="Aeronautical Engineering",
            source_ids=catalog_only,
            value={"direction": "aerospace_engineering"},
            review_note="项目名称与开设院系直接支持航空航天工程主方向。",
        ),
        _taxonomy_field(
            "taxonomy.secondary_directions",
            display_text="Master of Science in Aeronautical Engineering",
            source_ids=catalog_only,
            value={"directions": []},
            review_note="保持已复核候选矩阵口径，不从课程或院系名称推断次方向。",
        ),
        _requirement_field(
            "requirements.degree",
            status="confirmed",
            display_text=degree_display,
            source_ids=catalog_only,
            requirements=[
                _requirement(
                    "requirement.hkust.mscae.degree.2027.v1",
                    "degree",
                    degree_display,
                    catalog_only,
                    {
                        "node_id": "node.hkust.mscae.degree.all",
                        "operator": "all",
                        "children": [
                            {
                                "node_id": "node.hkust.mscae.degree.bachelor",
                                "operator": "enum_in",
                                "fact_path": "degree_level",
                                "allowed_values": ["bachelor"],
                            },
                            {
                                "node_id": "node.hkust.mscae.degree.recognition",
                                "operator": "manual_review",
                                "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                            },
                        ],
                    },
                )
            ],
        ),
        _requirement_field(
            "requirements.academic",
            status="confirmed",
            display_text=degree_display,
            source_ids=catalog_only,
            requirements=[
                _requirement(
                    "requirement.hkust.mscae.academic.2027.v1",
                    "academic",
                    degree_display,
                    catalog_only,
                    {
                        "node_id": "node.hkust.mscae.academic.classification",
                        "operator": "manual_review",
                        "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                    },
                )
            ],
        ),
        _requirement_field(
            "requirements.subject",
            status="confirmed",
            display_text=degree_display,
            source_ids=catalog_only,
            requirements=[
                _requirement(
                    "requirement.hkust.mscae.subject.2027.v1",
                    "subject",
                    degree_display,
                    catalog_only,
                    {
                        "node_id": "node.hkust.mscae.subject.any",
                        "operator": "any",
                        "children": [
                            {
                                "node_id": "node.hkust.mscae.subject.tags",
                                "operator": "set_intersects",
                                "fact_path": "degree_subject_tags",
                                "accepted_values": [
                                    "aerospace_engineering",
                                    "mechanical_engineering",
                                    "electronic_engineering",
                                    "automation",
                                    "computer_science",
                                    "artificial_intelligence",
                                    "data_science",
                                ],
                                "minimum_matches": 1,
                            },
                            {
                                "node_id": "node.hkust.mscae.subject.related",
                                "operator": "manual_review",
                                "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                            },
                        ],
                    },
                )
            ],
        ),
        _requirement_field(
            "requirements.prerequisite_courses",
            status="not_found_in_reviewed_sources",
            display_text="本次已核验的两页完整官网来源未找到指定先修课程；这不代表学校没有要求。",
            source_ids=all_source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.language",
            status="confirmed",
            display_text=language_display,
            source_ids=catalog_only,
            requirements=[
                _requirement(
                    "requirement.hkust.mscae.language.2027.v1",
                    "language",
                    language_display,
                    catalog_only,
                    {
                        "node_id": "node.hkust.mscae.language.any",
                        "operator": "any",
                        "children": [
                            {
                                "node_id": "node.hkust.mscae.language.ielts",
                                "operator": "language_minimum",
                                "test_type": "ielts",
                                "total_min": "6.5",
                                "component_mins": {
                                    "listening": "5.5",
                                    "reading": "5.5",
                                    "writing": "5.5",
                                    "speaking": "5.5",
                                },
                            },
                            {
                                "node_id": "node.hkust.mscae.language.other_routes",
                                "operator": "manual_review",
                                "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                            },
                        ],
                    },
                )
            ],
        ),
        _requirement_field(
            "requirements.work_experience",
            status="not_applicable",
            display_text="Fresh graduates who have good academic record are also our targets.",
            source_ids=program_only,
            reason_code="OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
            support_scope="applicability",
        ),
        _requirement_field(
            "requirements.materials",
            status="manual_review",
            display_text="材料要求未出现在本次已核验的两页官网来源中，保留人工核验。",
            source_ids=all_source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
    ]
    return _signed_pack(
        {
            "schema_version": "alpha_program_pack.v1",
            "pack_ref": "pack.hk.hkust.msc_aeronautical_engineering.2027.v1",
            "scope_snapshot_id": "scope.alpha.2027.v2",
            "scope_institution_ref": "institution.hk.hkust",
            "target_academic_year": ACADEMIC_YEAR,
            "program": {
                "program_ref": program_ref,
                "official_name": "MSc in Aeronautical Engineering",
                "institution_name": "The Hong Kong University of Science and Technology",
                "region": "hong_kong",
                "official_program_url": "https://seng.hkust.edu.hk/academics/taught-postgraduate/msc-ae",
                "registered_official_domain": "hkust.edu.hk",
                "official_domain_aliases": [],
                "degree_type": "taught_masters",
                "created_by": PREPARER,
                "creation_note": "第四阶段 8.1 首组，经三页官网人工核验后生成的 HKUST Candidate-only Program。",
            },
            "reviewed_source_ids": all_source_ids,
            "evidence": [catalog_evidence, program_evidence],
            "candidate": {
                "base_version_id": None,
                "fields": fields,
                "created_by": PREPARER,
                "creation_note": "第四阶段 8.1 HKUST 首组候选；冲突与缺失字段全部 fail closed。",
                "request_id": "request.phase4.batch8.1.hkust.mscae.v1",
            },
            "review": {
                "prepared_by": PREPARER,
                "prepared_at": PREPARED_AT,
                "reviewed_by": REVIEWER,
                "reviewed_at": REVIEWED_AT,
                "review_note": "产品负责人确认 HKUST 项目页与 2027/28 Catalog 手工核验通过；仅按冻结字段口径生成 Candidate Pack。",
                "review_status": "approved",
            },
            "pack_canonical_sha256": "0" * 64,
            "expected_semantic_content_sha256": "0" * 64,
        }
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    packs = {
        "hku_msc_computer_science_2027_v1.json": _hku_pack(),
        "hkust_msc_aeronautical_engineering_2027_v1.json": _hkust_pack(),
    }
    for filename, pack in packs.items():
        path = OUTPUT_DIR / filename
        path.write_text(
            json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"generated {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
