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
OUTPUT_PATH = OUTPUT_DIR / "manchester_msc_advanced_computer_science_2027_v1.json"
ACADEMIC_YEAR = "2027-28"
PROGRAM_REF = "program.uk.manchester.msc_advanced_computer_science"
PROGRAM_URL = (
    "https://www.manchester.ac.uk/study/masters/courses/list/21573/"
    "msc-advanced-computer-science/"
)
PREPARED_AT = "2026-09-03T20:00:00+08:00"
REVIEWED_AT = "2026-09-03T20:15:00+08:00"
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
    page_title: str,
    excerpt: str,
    role: str,
) -> dict:
    return {
        "schema_version": "source_evidence.v2",
        "applicable_academic_year": ACADEMIC_YEAR,
        "id": evidence_id,
        "program_id": PROGRAM_REF,
        "source_type": "official_program_page",
        "url": PROGRAM_URL,
        "official_domain": "www.manchester.ac.uk",
        "page_title": page_title,
        "excerpt": excerpt,
        "snapshot_sha256": _sha256(excerpt),
        "source_version": "2027 entry page manually verified on 2026-09-03",
        "captured_at": PREPARED_AT,
        "verified_at": REVIEWED_AT,
        "verified_by": PREPARER,
        "review_due_at": "2026-10-03T20:15:00+08:00",
        "expires_at": "2026-12-02T20:15:00+08:00",
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


def _build_pack() -> dict:
    page_title = (
        "MSc Advanced Computer Science (2027 entry) | "
        "The University of Manchester"
    )
    program_id = "evidence.manchester.advanced_cs.program.2027.v1"
    admissions_id = "evidence.manchester.advanced_cs.admissions.2027.v1"
    language_id = "evidence.manchester.advanced_cs.language.2027.v1"
    curriculum_id = "evidence.manchester.advanced_cs.curriculum.2027.v1"
    all_source_ids = sorted(
        [program_id, admissions_id, language_id, curriculum_id]
    )

    program_excerpt = "\n".join(
        [
            "Master of Science",
            "MSc Advanced Computer Science",
            "Year of entry: 2027",
            "Duration: 12 months full-time",
            "Full-time: In person",
            "Department of Computer Science",
        ]
    )
    admissions_excerpt = "\n".join(
        [
            "Successful applicants typically hold a First-class honours degree (70% average) from a UK university, or the overseas equivalent, in a Computer Science degree with a minimum of 50% Computer Science content.",
            "We require that all applicants have a strong background in Computer Science reflected, for example, in solid programming and software development skills.",
            "China: a minimum of 87% in a 4-year bachelor's degree from a well ranked institution.",
            "Applications for 2027 entry:",
            "Stage 1: Application received by 6 November 2026; Decision by 8 January 2027.",
            "Stage 2: Application received by 1 January 2027; Decision by 5 March 2027.",
            "Stage 3: Application received by 26 Feb 2027; Decision by 30 April 2027.",
            "Stage 4: Application received by 21 May 2027; Decision by 18 June 2027.",
            "Applications received after 21 May 2027 will be considered depending on course availability.",
            "We require official Bachelor degree transcripts and supporting documents listed on the programme page.",
            "A CV is required if you graduated more than three years ago.",
            "References and personal statements are not required for your application to this programme.",
            "There is no application fee for this programme.",
            "Applications for deferred entry are not accepted for this course.",
        ]
    )
    language_excerpt = "\n".join(
        [
            "IELTS: overall score of 7.0 with no sub-test below 6.5.",
            "TOEFL iBT: at least 100 overall with no sub-test less than 22. We do not accept 'MyBestScore'. We do not accept TOEFL iBT Home Edition.",
            "Pearson PTE: at least 76 overall with no sub-test below 70.",
            "Your English Language test report must be valid on the start date of the course.",
        ]
    )
    curriculum_excerpt = "\n".join(
        [
            "Our flagship Computer Science course enables you to explore diverse specialisms in a comprehensive curriculum.",
            "This programme will provide training and experience of advanced computational techniques.",
            "Masters Project (60 Credits)",
            "Introduction to Cryptography",
            "Network Security",
            "Data Engineering Concepts",
            "Reasoning and Learning under Uncertainty",
        ]
    )
    evidence = [
        _evidence(
            evidence_id=admissions_id,
            page_title=page_title,
            excerpt=admissions_excerpt,
            role="admissions_policy",
        ),
        _evidence(
            evidence_id=curriculum_id,
            page_title=page_title,
            excerpt=curriculum_excerpt,
            role="curriculum",
        ),
        _evidence(
            evidence_id=language_id,
            page_title=page_title,
            excerpt=language_excerpt,
            role="language_policy",
        ),
        _evidence(
            evidence_id=program_id,
            page_title=page_title,
            excerpt=program_excerpt,
            role="program",
        ),
    ]

    intake_missing = (
        "本次已核验的 2027 官网正文确认 entry year，但未确认具体入学月份；"
        "不得由 2026 参考费用或英国学年惯例推断。"
    )
    prerequisite_review = (
        "官网要求 strong Computer Science background、solid programming and software "
        "development skills，但没有可无损编码的课程数量门槛，保留人工核验。"
    )
    work_review = (
        "官网未设置通用工作经验年限；毕业超过三年的申请人需提交 CV，相关经验用于个案评估。"
    )
    materials_review = (
        "官网要求成绩单、条件性加权均分文件、学位证或在读课程清单等材料，并明确不要求推荐信和个人陈述；"
        "当前材料布尔合同不能无损表达完整清单，保留人工核验。"
    )

    degree_display = (
        "Successful applicants typically hold a First-class honours degree (70% "
        "average) from a UK university, or the overseas equivalent, in a Computer "
        "Science degree with a minimum of 50% Computer Science content."
    )
    academic_display = (
        "China: a minimum of 87% in a 4-year bachelor's degree from a well ranked institution."
    )
    subject_display = (
        "Computer Science degree with a minimum of 50% Computer Science content."
    )
    language_display = "IELTS: overall score of 7.0 with no sub-test below 6.5."

    fields = [
        _catalog_field(
            "catalog.academic_year",
            status="confirmed",
            display_text="Year of entry: 2027",
            source_ids=[program_id],
            value={"academic_year": ACADEMIC_YEAR},
            review_note="官网以 2027 entry 表述目标入学周期，映射为 2027-28 学年。",
        ),
        _catalog_field(
            "catalog.degree_type",
            status="confirmed",
            display_text="Master of Science",
            source_ids=[program_id],
            value={"degree_type": "taught_masters"},
        ),
        _catalog_field(
            "catalog.department",
            status="confirmed",
            display_text="Department of Computer Science",
            source_ids=[program_id],
            value={"department_name": "Department of Computer Science"},
        ),
        _catalog_field(
            "catalog.duration",
            status="confirmed",
            display_text="Duration: 12 months full-time",
            source_ids=[program_id],
            value={"months": 12, "study_mode": "full_time"},
        ),
        _catalog_field(
            "catalog.intake",
            status="not_found_in_reviewed_sources",
            display_text=intake_missing,
            source_ids=all_source_ids,
            reason_code="OFFICIAL_RULE_NOT_FOUND",
            support_scope="coverage",
        ),
        _catalog_field(
            "catalog.application_status",
            status="confirmed",
            display_text="Applications for 2027 entry:",
            source_ids=[admissions_id],
            value={
                "status": "open",
                "opens_on": None,
                "closes_on": "2027-05-21",
            },
            review_note=(
                "官网提供 Apply online 与四轮 2027 截止日期；21 May 2027 后仅视余位酌情考虑。"
            ),
        ),
        _taxonomy_field(
            "taxonomy.primary_direction",
            display_text="MSc Advanced Computer Science",
            source_ids=[program_id, curriculum_id],
            value={"direction": "computer_science"},
            review_note="项目名称、CS 本科门槛和高级计算课程共同支持计算机科学主方向。",
        ),
        _taxonomy_field(
            "taxonomy.secondary_directions",
            display_text=(
                "This programme will provide training and experience of advanced "
                "computational techniques."
            ),
            source_ids=[curriculum_id],
            value={"directions": []},
            review_note="保持 8B 复核矩阵口径，不因可选 AI 或数据课程推断次方向。",
        ),
        _requirement_field(
            "requirements.degree",
            status="confirmed",
            display_text=degree_display,
            source_ids=[admissions_id],
            requirements=[
                _requirement(
                    "requirement.manchester.advanced_cs.degree.2027.v1",
                    "degree",
                    degree_display,
                    [admissions_id],
                    {
                        "node_id": "node.manchester.advanced_cs.degree.all",
                        "operator": "all",
                        "children": [
                            {
                                "node_id": "node.manchester.advanced_cs.degree.bachelor",
                                "operator": "enum_in",
                                "fact_path": "degree_level",
                                "allowed_values": ["bachelor"],
                            },
                            {
                                "node_id": "node.manchester.advanced_cs.degree.equivalence",
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
            display_text=academic_display,
            source_ids=[admissions_id],
            requirements=[
                _requirement(
                    "requirement.manchester.advanced_cs.academic.2027.v1",
                    "academic",
                    academic_display,
                    [admissions_id],
                    {
                        "node_id": "node.manchester.advanced_cs.academic.region",
                        "operator": "case",
                        "selector_path": "applicant_region",
                        "cases": {
                            "china_mainland": {
                                "node_id": "node.manchester.advanced_cs.academic.china",
                                "operator": "numeric_min",
                                "fact_path": "academic_record.value",
                                "minimum": "87",
                                "scale": "100",
                            }
                        },
                        "default": {
                            "node_id": "node.manchester.advanced_cs.academic.other",
                            "operator": "manual_review",
                            "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                        },
                    },
                )
            ],
        ),
        _requirement_field(
            "requirements.subject",
            status="confirmed",
            display_text=subject_display,
            source_ids=[admissions_id],
            requirements=[
                _requirement(
                    "requirement.manchester.advanced_cs.subject.2027.v1",
                    "subject",
                    subject_display,
                    [admissions_id],
                    {
                        "node_id": "node.manchester.advanced_cs.subject.all",
                        "operator": "all",
                        "children": [
                            {
                                "node_id": "node.manchester.advanced_cs.subject.cs",
                                "operator": "set_intersects",
                                "fact_path": "degree_subject_tags",
                                "accepted_values": ["computer_science"],
                                "minimum_matches": 1,
                            },
                            {
                                "node_id": "node.manchester.advanced_cs.subject.content",
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
            status="manual_review",
            display_text=prerequisite_review,
            source_ids=[admissions_id],
            reason_code="OFFICIAL_RULE_AMBIGUOUS",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.language",
            status="confirmed",
            display_text=language_display,
            source_ids=[language_id],
            requirements=[
                _requirement(
                    "requirement.manchester.advanced_cs.language.2027.v1",
                    "language",
                    language_display,
                    [language_id],
                    {
                        "node_id": "node.manchester.advanced_cs.language.any",
                        "operator": "any",
                        "children": [
                            {
                                "node_id": "node.manchester.advanced_cs.language.ielts",
                                "operator": "language_minimum",
                                "test_type": "ielts",
                                "total_min": "7.0",
                                "component_mins": {
                                    "listening": "6.5",
                                    "reading": "6.5",
                                    "writing": "6.5",
                                    "speaking": "6.5",
                                },
                            },
                            {
                                "node_id": "node.manchester.advanced_cs.language.toefl_all",
                                "operator": "all",
                                "children": [
                                    {
                                        "node_id": "node.manchester.advanced_cs.language.toefl",
                                        "operator": "language_minimum",
                                        "test_type": "toefl",
                                        "total_min": "100",
                                        "component_mins": {
                                            "listening": "22",
                                            "reading": "22",
                                            "writing": "22",
                                            "speaking": "22",
                                        },
                                    },
                                    {
                                        "node_id": "node.manchester.advanced_cs.language.toefl_route",
                                        "operator": "manual_review",
                                        "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                                    },
                                ],
                            },
                            {
                                "node_id": "node.manchester.advanced_cs.language.pte",
                                "operator": "language_minimum",
                                "test_type": "pte",
                                "total_min": "76",
                                "component_mins": {
                                    "listening": "70",
                                    "reading": "70",
                                    "writing": "70",
                                    "speaking": "70",
                                },
                            },
                        ],
                    },
                )
            ],
        ),
        _requirement_field(
            "requirements.work_experience",
            status="manual_review",
            display_text=work_review,
            source_ids=[admissions_id],
            reason_code="OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
            support_scope="coverage",
        ),
        _requirement_field(
            "requirements.materials",
            status="manual_review",
            display_text=materials_review,
            source_ids=[admissions_id],
            reason_code="OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
            support_scope="coverage",
        ),
    ]

    return _signed_pack(
        {
            "schema_version": "alpha_program_pack.v1",
            "pack_ref": "pack.uk.manchester.msc_advanced_computer_science.2027.v1",
            "scope_snapshot_id": "scope.alpha.2027.v2",
            "scope_institution_ref": "institution.uk.manchester",
            "target_academic_year": ACADEMIC_YEAR,
            "program": {
                "program_ref": PROGRAM_REF,
                "official_name": "MSc Advanced Computer Science",
                "institution_name": "The University of Manchester",
                "region": "united_kingdom",
                "official_program_url": PROGRAM_URL,
                "registered_official_domain": "manchester.ac.uk",
                "official_domain_aliases": [],
                "degree_type": "taught_masters",
                "created_by": PREPARER,
                "creation_note": (
                    "第四阶段 8.6 目标学年正负分流验证的 Manchester "
                    "Advanced Computer Science Candidate-only Program。"
                ),
            },
            "reviewed_source_ids": all_source_ids,
            "evidence": evidence,
            "candidate": {
                "base_version_id": None,
                "fields": fields,
                "created_by": PREPARER,
                "creation_note": (
                    "第四阶段 8.6 Manchester Advanced CS 2027 候选；"
                    "Edinburgh 阻塞项目未生成 Pack，费用字段未进入 Registry。"
                ),
                "request_id": "request.phase4.batch8.6.manchester.advanced_cs.v1",
            },
            "review": {
                "prepared_by": PREPARER,
                "prepared_at": PREPARED_AT,
                "reviewed_by": REVIEWER,
                "reviewed_at": REVIEWED_AT,
                "review_note": (
                    "产品负责人确认 8.6 来源、字段与逐项目分流；"
                    "仅 Manchester Advanced CS 进入 Candidate-only 生产，"
                    "2026 参考学费不得沿用。"
                ),
                "review_status": "approved",
            },
            "pack_canonical_sha256": "0" * 64,
            "expected_semantic_content_sha256": "0" * 64,
        }
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pack = _build_pack()
    OUTPUT_PATH.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"generated {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
