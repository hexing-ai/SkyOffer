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
PREPARED_AT = "2026-09-03T16:05:00+08:00"
REVIEWED_AT = "2026-09-03T16:18:00+08:00"
PREPARER = "actor.data_preparer.codex"
REVIEWER = "actor.domain_reviewer.product_owner"
POLICY_URL = (
    "https://fytgs.hkust.edu.hk/admissions/Admission-to-Hong-Kong-Campus/"
    "submitting-an-application/admission-requirements"
)


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
    reason = (
        None
        if reason_code is None
        else {"reason_code": reason_code, "detail": display_text}
    )
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
    reason = (
        None
        if reason_code is None
        else {"reason_code": reason_code, "detail": display_text}
    )
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
    *,
    applicability: dict | None = None,
) -> dict:
    return {
        "requirement_id": requirement_id,
        "requirement_type": requirement_type,
        "is_hard": True,
        "applicability": applicability,
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
        "review_due_at": "2026-10-03T16:18:00+08:00",
        "expires_at": "2026-12-02T16:18:00+08:00",
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
    return raw


def _common_policy_excerpt() -> str:
    return "\n".join(
        [
            "Applicants seeking admissions to a master's degree or postgraduate diploma program should have:",
            "Obtained a bachelor’s degree from a recognized institution, or an approved equivalent qualification.",
            "Applicants have to fulfill English Language requirements with one of the following proficiency attainments:",
            "TOEFL Internet-based Test (iBT): 80 (for tests taken prior to 21 January 2026) *",
            "4.5 (for tests taken from 21 January 2026 onwards) *",
            "IELTS (Academic Module): Overall score: 6.5 and all sub-score: 5.5 *",
            "* Refers to scores in one single attempt only. Test at home option is not accepted.",
            "Applicants are not required to present TOEFL or IELTS score if",
            "Their first language is English, or",
            "Their bachelor's degree (or equivalent qualification) was awarded by an institution where the medium of instruction was English.",
        ]
    )


def _common_degree_field(prefix: str, policy_id: str) -> dict:
    display = "Obtained a bachelor’s degree from a recognized institution, or an approved equivalent qualification."
    return _requirement_field(
        "requirements.degree",
        status="confirmed",
        display_text=display,
        source_ids=[policy_id],
        requirements=[
            _requirement(
                f"requirement.hkust.{prefix}.degree.2027.v1",
                "degree",
                display,
                [policy_id],
                {
                    "node_id": f"node.hkust.{prefix}.degree.all",
                    "operator": "all",
                    "children": [
                        {
                            "node_id": f"node.hkust.{prefix}.degree.bachelor",
                            "operator": "enum_in",
                            "fact_path": "degree_level",
                            "allowed_values": ["bachelor"],
                        },
                        {
                            "node_id": f"node.hkust.{prefix}.degree.recognition",
                            "operator": "manual_review",
                            "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                        },
                    ],
                },
            )
        ],
    )


def _common_language_field(prefix: str, policy_id: str) -> dict:
    display = "IELTS (Academic Module): Overall score: 6.5 and all sub-score: 5.5 *"
    return _requirement_field(
        "requirements.language",
        status="confirmed",
        display_text=display,
        source_ids=[policy_id],
        requirements=[
            _requirement(
                f"requirement.hkust.{prefix}.language.2027.v1",
                "language",
                display,
                [policy_id],
                {
                    "node_id": f"node.hkust.{prefix}.language.any",
                    "operator": "any",
                    "children": [
                        {
                            "node_id": f"node.hkust.{prefix}.language.ielts",
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
                            "node_id": f"node.hkust.{prefix}.language.other_routes",
                            "operator": "manual_review",
                            "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                        },
                    ],
                },
            )
        ],
    )


def _subject_field(prefix: str, program_id: str, display: str) -> dict:
    return _requirement_field(
        "requirements.subject",
        status="confirmed",
        display_text=display,
        source_ids=[program_id],
        requirements=[
            _requirement(
                f"requirement.hkust.{prefix}.subject.2027.v1",
                "subject",
                display,
                [program_id],
                {
                    "node_id": f"node.hkust.{prefix}.subject.any",
                    "operator": "any",
                    "children": [
                        {
                            "node_id": f"node.hkust.{prefix}.subject.tags",
                            "operator": "set_intersects",
                            "fact_path": "degree_subject_tags",
                            "accepted_values": [
                                "computer_science",
                                "electronic_engineering",
                                "artificial_intelligence",
                                "data_science",
                            ],
                            "minimum_matches": 1,
                        },
                        {
                            "node_id": f"node.hkust.{prefix}.subject.related",
                            "operator": "manual_review",
                            "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                        },
                    ],
                },
            )
        ],
    )


def _pack(*, artificial_intelligence: bool) -> dict:
    prefix = "mscai" if artificial_intelligence else "mscit"
    slug = "msc_artificial_intelligence" if artificial_intelligence else "msc_information_technology"
    short_name = "Artificial Intelligence" if artificial_intelligence else "Information Technology"
    program_ref = f"program.hk.hkust.{slug}"
    pack_ref = f"pack.hk.hkust.{slug}.2027.v1"
    program_id = f"evidence.hkust.{prefix}.program.2027.v1"
    catalog_id = f"evidence.hkust.{prefix}.catalog.2027.v1"
    policy_id = f"evidence.hkust.{prefix}.admissions_policy.2027.v1"
    all_source_ids = sorted([program_id, catalog_id, policy_id])

    if artificial_intelligence:
        subject_display = "Applicants must possess a bachelor’s degree in Computer Engineering, Computer Science or a related discipline."
        program_excerpt_lines = [
            "MSc in Artificial Intelligence",
            "It is tailored to both recent graduates and working professionals seeking to enhance their expertise in this exciting and rapidly evolving field.",
            "Students are required to complete a total of 30 credits of coursework, including 12 credits of core courses and 18 credits of elective courses.",
            subject_display,
            "Applicants with a bachelor’s degree in other disciplines must have at least two years of post-qualification work experience relevant to the program.",
            "The nominal program fee for 2027/28 Fall intake is HK$400,000 (full-time study to be paid in 2 installments and part-time study to be paid in 4 installments).",
            "All applications are considered on a competitive and rolling basis.",
            "For 2027/28 Fall intake (September 2027)",
        ]
        catalog_duration_full = "Full-time : 1 year"
        catalog_duration_part = "Part-time : 2 years"
    else:
        subject_display = "Applicants must possess a bachelor’s degree in Computer Engineering or Computer Science, or a related field from a recognized university or tertiary institution."
        program_excerpt_lines = [
            "MSc in Information Technology",
            "Students are required to complete a total of 30 credits of coursework.",
            subject_display,
            "The nominal program fee for 2027/28 Fall intake for full-time study is HK$320,000 (paid in 2 installments) and part-time study is HK$260,000 (paid in 4 installments) respectively.",
            "All applications are considered on a competitive and rolling basis.",
            "For 2027/28 Fall intake (September 2027)",
        ]
        catalog_duration_full = "Full-time: 1 year"
        catalog_duration_part = "Part-time: 2 years"

    program_excerpt = "\n".join(program_excerpt_lines)
    catalog_excerpt = "\n".join(
        [
            "Postgraduate Programs 2027/28",
            f"Master of Science Program in {short_name}",
            f"Master of Science in {short_name}",
            "Both full- and part-time",
            catalog_duration_full,
            catalog_duration_part,
            "Department of Computer Science and Engineering",
        ]
    )
    evidence = [
        _evidence(
            evidence_id=catalog_id,
            program_id=program_ref,
            url=f"https://prog-crs.hkust.edu.hk/pgprog/2027-28/{'msc-ai' if artificial_intelligence else 'msc-it'}",
            official_domain="prog-crs.hkust.edu.hk",
            page_title="Program & Course Catalog",
            excerpt=catalog_excerpt,
            source_type="official_policy_page",
            source_version="Postgraduate Programs 2027/28 manually verified on 2026-09-03",
            role="language_policy",
        ),
        _evidence(
            evidence_id=policy_id,
            program_id=program_ref,
            url=POLICY_URL,
            official_domain="fytgs.hkust.edu.hk",
            page_title="Admissions Requirements | HKUST Fok Ying Tung Graduate School",
            excerpt=_common_policy_excerpt(),
            source_type="official_policy_page",
            source_version="Continuous HKUST admissions policy approved for 2027/28 on 2026-09-03",
            role="admissions_policy",
        ),
        _evidence(
            evidence_id=program_id,
            program_id=program_ref,
            url=f"https://seng.hkust.edu.hk/academics/taught-postgraduate/{'msc-ai' if artificial_intelligence else 'msc-it'}",
            official_domain="seng.hkust.edu.hk",
            page_title=f"MSc in {short_name} | HKUST School of Engineering",
            excerpt=program_excerpt,
            source_type="official_program_page",
            source_version="2027/28 Fall intake page manually verified on 2026-09-03",
            role="program",
        ),
    ]

    not_found = "本次已核验的完整官网来源未找到该项 2027/28 明确要求；这不代表学校没有要求。"
    materials_review = "材料要求未在本次已核验的完整官网来源正文中确认，保留人工核验。"
    catalog_only = [catalog_id]
    program_only = [program_id]
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
            display_text=f"Master of Science in {short_name}",
            source_ids=catalog_only,
            value={"degree_type": "taught_masters"},
        ),
        _catalog_field(
            "catalog.department",
            status="confirmed",
            display_text="Department of Computer Science and Engineering",
            source_ids=catalog_only,
            value={"department_name": "Department of Computer Science and Engineering"},
        ),
        _catalog_field(
            "catalog.duration",
            status="confirmed",
            display_text=catalog_duration_full,
            source_ids=catalog_only,
            value={"months": 12, "study_mode": "mixed"},
            review_note="同页同时确认全日制 1 年与非全日制 2 年；结构化主时长按全日制 12 个月，模式记 mixed。",
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
            display_text="All applications are considered on a competitive and rolling basis.",
            source_ids=program_only,
            value={"status": "rolling", "opens_on": None, "closes_on": None},
            review_note="官方页存在多轮日期；当前合同只结构化 rolling，不压缩为单一 closes_on。",
        ),
        _taxonomy_field(
            "taxonomy.primary_direction",
            display_text=short_name,
            source_ids=catalog_only,
            value={
                "direction": (
                    "artificial_intelligence"
                    if artificial_intelligence
                    else "computer_science"
                )
            },
            review_note=f"项目名称直接支持{short_name}主方向。",
        ),
        _taxonomy_field(
            "taxonomy.secondary_directions",
            display_text=f"Master of Science in {short_name}",
            source_ids=catalog_only,
            value={"directions": []},
            review_note="保持已复核候选矩阵口径，不从课程列表推断次方向。",
        ),
        _common_degree_field(prefix, policy_id),
        _requirement_field(
            "requirements.academic",
            status="not_found_in_reviewed_sources",
            display_text=not_found,
            source_ids=all_source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _subject_field(prefix, program_id, subject_display),
        _requirement_field(
            "requirements.prerequisite_courses",
            status="not_found_in_reviewed_sources",
            display_text=not_found,
            source_ids=all_source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _common_language_field(prefix, policy_id),
    ]

    if artificial_intelligence:
        work_display = "Applicants with a bachelor’s degree in other disciplines must have at least two years of post-qualification work experience relevant to the program."
        fields.append(
            _requirement_field(
                "requirements.work_experience",
                status="confirmed",
                display_text=work_display,
                source_ids=program_only,
                requirements=[
                    _requirement(
                        "requirement.hkust.mscai.work_experience.2027.v1",
                        "work_experience",
                        work_display,
                        program_only,
                        {
                            "node_id": "node.hkust.mscai.work_experience.minimum",
                            "operator": "duration_min_months",
                            "fact_path": "work_experience_months",
                            "minimum_months": 24,
                        },
                        applicability={
                            "node_id": "node.hkust.mscai.work_experience.other_subject",
                            "operator": "manual_review",
                            "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                        },
                    )
                ],
            )
        )
    else:
        fields.append(
            _requirement_field(
                "requirements.work_experience",
                status="not_found_in_reviewed_sources",
                display_text=not_found,
                source_ids=all_source_ids,
                reason_code="OFFICIAL_RULE_NOT_FOUND",
                support_scope="coverage",
            )
        )

    fields.append(
        _requirement_field(
            "requirements.materials",
            status="manual_review",
            display_text=materials_review,
            source_ids=all_source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        )
    )

    return _signed_pack(
        {
            "schema_version": "alpha_program_pack.v1",
            "pack_ref": pack_ref,
            "scope_snapshot_id": "scope.alpha.2027.v2",
            "scope_institution_ref": "institution.hk.hkust",
            "target_academic_year": ACADEMIC_YEAR,
            "program": {
                "program_ref": program_ref,
                "official_name": f"MSc in {short_name}",
                "institution_name": "The Hong Kong University of Science and Technology",
                "region": "hong_kong",
                "official_program_url": f"https://seng.hkust.edu.hk/academics/taught-postgraduate/{'msc-ai' if artificial_intelligence else 'msc-it'}",
                "registered_official_domain": "hkust.edu.hk",
                "official_domain_aliases": [],
                "degree_type": "taught_masters",
                "created_by": PREPARER,
                "creation_note": f"第四阶段 8.2 同校相邻项目隔离验证的 HKUST {short_name} Candidate-only Program。",
            },
            "reviewed_source_ids": all_source_ids,
            "evidence": evidence,
            "candidate": {
                "base_version_id": None,
                "fields": fields,
                "created_by": PREPARER,
                "creation_note": f"第四阶段 8.2 HKUST {short_name} 候选；项目规则与共用政策分别引用并 fail closed。",
                "request_id": f"request.phase4.batch8.2.hkust.{prefix}.v1",
            },
            "review": {
                "prepared_by": PREPARER,
                "prepared_at": PREPARED_AT,
                "reviewed_by": REVIEWER,
                "reviewed_at": REVIEWED_AT,
                "review_note": "产品负责人确认 8.2 来源与字段口径，并批准持续招生要求页用于 2027/28；仅生成 Candidate Pack。",
                "review_status": "approved",
            },
            "pack_canonical_sha256": "0" * 64,
            "expected_semantic_content_sha256": "0" * 64,
        }
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    packs = {
        "hkust_msc_information_technology_2027_v1.json": _pack(
            artificial_intelligence=False
        ),
        "hkust_msc_artificial_intelligence_2027_v1.json": _pack(
            artificial_intelligence=True
        ),
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
