from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.scripts.generate_phase4_batch_8_6_pack import (
    _catalog_field,
    _requirement,
    _requirement_field,
    _signed_pack,
    _taxonomy_field,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "backend" / "data" / "alpha_v1" / "programs"
OUTPUT_PATH = OUTPUT_DIR / "manchester_msc_aerospace_engineering_2027_v1.json"
ACADEMIC_YEAR = "2027-28"
PROGRAM_REF = "program.uk.manchester.msc_aerospace_engineering"
PROGRAM_URL = (
    "https://www.manchester.ac.uk/study/masters/courses/list/08025/"
    "msc-aerospace-engineering/"
)
PREPARED_AT = "2026-09-03T22:00:00+08:00"
REVIEWED_AT = "2026-09-03T22:15:00+08:00"
PREPARER = "actor.data_preparer.codex"
REVIEWER = "actor.domain_reviewer.product_owner"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence(
    *, evidence_id: str, page_title: str, excerpt: str, role: str
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
        "review_due_at": "2026-10-03T22:15:00+08:00",
        "expires_at": "2026-12-02T22:15:00+08:00",
        "availability_at_verification": "available",
        "capture_method": "manual_browser",
        "hash_scope": "normalized_excerpt",
        "reviewed_source_role": role,
    }


def _build_pack() -> dict:
    page_title = (
        "MSc Aerospace Engineering (2027 entry) | "
        "The University of Manchester"
    )
    program_id = "evidence.manchester.aerospace.program.2027.v1"
    admissions_id = "evidence.manchester.aerospace.admissions.2027.v1"
    language_id = "evidence.manchester.aerospace.language.2027.v1"
    curriculum_id = "evidence.manchester.aerospace.curriculum.2027.v1"
    all_source_ids = sorted(
        [program_id, admissions_id, language_id, curriculum_id]
    )

    program_excerpt = "\n".join(
        [
            "Master of Science",
            "MSc Aerospace Engineering",
            "Year of entry: 2027",
            "Duration: 12 months [Full-Time]",
            "Full-time: In person",
            "Department of Mechanical and Aerospace Engineering",
            "The Aerospace Engineering MSc is a full-time course which is studied over 12 months, commencing each year in September.",
        ]
    )
    admissions_excerpt = "\n".join(
        [
            "The standard academic entry requirement for this programme is an Upper Second Class UK Honours degree or international equivalent in a relevant science or engineering discipline.",
            "Please note that we consider grades achieved in key relevant modules in your undergraduate degree as well as the overall degree result.",
            "We operate a non-staged admissions process for this programme.",
            "Provided your application is complete, we aim to give you a decision on your application within 2 months from the date on which it was submitted.",
            "Applicants with a conditional offer must provide evidence that they have met all conditions by 31 July 2027.",
            "We require the following documents before we can consider your application: transcript and translations where required; weighted average verification where required; final-year module list if still studying; degree certificate if graduated; and a CV if you graduated more than three years ago.",
            "References and personal statements are not required for your application for this programme.",
            "If you graduated more than three years ago, we will also consider the information contained on your CV and any relevant work experience to assess if you are still able to fulfil the entry criteria.",
            "Applications for deferred entry are not accepted for this course.",
        ]
    )
    language_excerpt = "\n".join(
        [
            "IELTS: overall score of 7.0 with no sub-test below 6.5",
            "TOEFL iBT: at least 100 overall with no sub-test less than 22. We do not accept 'MyBestScore'. We do not accept TOEFL iBT Home Edition.",
            "Pearson PTE: at least 76 overall with no sub-test below 70",
            "Your English Language test report must be valid on the start date of the course.",
        ]
    )
    curriculum_excerpt = "\n".join(
        [
            "Our comprehensive course prepares you for a career in everything from helicopters and heat transfer to aerodynamics and aerospace design.",
            "You can specialise in computational fluid dynamics, flow diagnostics and measurements, aero structures, satellite design.",
            "Aerospace Group Design Project (30 Credits, Mandatory)",
            "Dissertation (Aerospace Engineering) (60 Credits, Mandatory)",
            "Experimental Methods (MSc Aerospace Engineering) (15 Credits, Mandatory)",
            "Advanced Computational Fluid Dynamics (15 Credits, Optional)",
            "Space Systems (15 Credits, Optional)",
            "Helicopters (15 Credits, Optional)",
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

    degree_display = (
        "The standard academic entry requirement for this programme is an Upper "
        "Second Class UK Honours degree or international equivalent in a relevant "
        "science or engineering discipline."
    )
    academic_display = degree_display
    subject_display = degree_display
    prerequisite_review = (
        "官网要求审核 key relevant modules 的成绩，但未列出可无损编码的课程名称、数量或"
        "最低分，保留人工核验。"
    )
    work_review = (
        "官网未设置通用工作经验年限；毕业超过三年的申请人需提交 CV，相关经验用于个案评估。"
    )
    materials_review = (
        "官网要求成绩单、条件性加权均分文件、学位证或在读课程清单等材料，并明确不要求"
        "推荐信和个人陈述；当前材料布尔合同不能无损表达完整清单，保留人工核验。"
    )

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
            display_text="Department of Mechanical and Aerospace Engineering",
            source_ids=[program_id],
            value={
                "department_name": "Department of Mechanical and Aerospace Engineering"
            },
        ),
        _catalog_field(
            "catalog.duration",
            status="confirmed",
            display_text="Duration: 12 months [Full-Time]",
            source_ids=[program_id],
            value={"months": 12, "study_mode": "full_time"},
        ),
        _catalog_field(
            "catalog.intake",
            status="confirmed",
            display_text="commencing each year in September",
            source_ids=[program_id],
            value={"intake_months": [9]},
            review_note=(
                "2027 entry 页面同页说明本课程每年 September 开始，映射为 2027 年 9 月入学。"
            ),
        ),
        _catalog_field(
            "catalog.application_status",
            status="confirmed",
            display_text="We operate a non-staged admissions process for this programme.",
            source_ids=[admissions_id],
            value={"status": "open", "opens_on": None, "closes_on": None},
            review_note=(
                "官网提供 Apply Online 且采用 non-staged admissions；未公布统一截止日，"
                "名额可能提前用尽。"
            ),
        ),
        _taxonomy_field(
            "taxonomy.primary_direction",
            display_text="MSc Aerospace Engineering",
            source_ids=[program_id, curriculum_id],
            value={"direction": "aerospace_engineering"},
            review_note=(
                "项目名称、航空院系和航空设计、空气动力学及航天课程共同支持航空工程主方向。"
            ),
        ),
        _taxonomy_field(
            "taxonomy.secondary_directions",
            display_text="MSc Aerospace Engineering",
            source_ids=[curriculum_id],
            value={"directions": []},
            review_note=(
                "保持 8B 复核矩阵口径；不因单门机器人、直升机课程或无人机职业示例推断低空次方向。"
            ),
        ),
        _requirement_field(
            "requirements.degree",
            status="confirmed",
            display_text=degree_display,
            source_ids=[admissions_id],
            requirements=[
                _requirement(
                    "requirement.manchester.aerospace.degree.2027.v1",
                    "degree",
                    degree_display,
                    [admissions_id],
                    {
                        "operator": "all",
                        "node_id": "node.manchester.aerospace.degree.all",
                        "children": [
                            {
                                "operator": "enum_in",
                                "node_id": "node.manchester.aerospace.degree.bachelor",
                                "fact_path": "degree_level",
                                "allowed_values": ["bachelor"],
                            },
                            {
                                "operator": "manual_review",
                                "node_id": "node.manchester.aerospace.degree.equivalence",
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
                    "requirement.manchester.aerospace.academic.2027.v1",
                    "academic",
                    academic_display,
                    [admissions_id],
                    {
                        "operator": "manual_review",
                        "node_id": "node.manchester.aerospace.academic.equivalence",
                        "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
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
                    "requirement.manchester.aerospace.subject.2027.v1",
                    "subject",
                    subject_display,
                    [admissions_id],
                    {
                        "operator": "any",
                        "node_id": "node.manchester.aerospace.subject.any",
                        "children": [
                            {
                                "operator": "set_intersects",
                                "node_id": "node.manchester.aerospace.subject.tags",
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
                                "operator": "manual_review",
                                "node_id": "node.manchester.aerospace.subject.other",
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
            display_text="IELTS: overall score of 7.0 with no sub-test below 6.5",
            source_ids=[language_id],
            requirements=[
                _requirement(
                    "requirement.manchester.aerospace.language.2027.v1",
                    "language",
                    "IELTS: overall score of 7.0 with no sub-test below 6.5",
                    [language_id],
                    {
                        "operator": "any",
                        "node_id": "node.manchester.aerospace.language.any",
                        "children": [
                            {
                                "operator": "language_minimum",
                                "node_id": "node.manchester.aerospace.language.ielts",
                                "test_type": "ielts",
                                "total_min": "7.0",
                                "component_mins": {
                                    "listening": "6.5",
                                    "reading": "6.5",
                                    "speaking": "6.5",
                                    "writing": "6.5",
                                },
                            },
                            {
                                "operator": "all",
                                "node_id": "node.manchester.aerospace.language.toefl_all",
                                "children": [
                                    {
                                        "operator": "language_minimum",
                                        "node_id": "node.manchester.aerospace.language.toefl",
                                        "test_type": "toefl",
                                        "total_min": "100",
                                        "component_mins": {
                                            "listening": "22",
                                            "reading": "22",
                                            "speaking": "22",
                                            "writing": "22",
                                        },
                                    },
                                    {
                                        "operator": "manual_review",
                                        "node_id": "node.manchester.aerospace.language.toefl_route",
                                        "reason_code": "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
                                    },
                                ],
                            },
                            {
                                "operator": "language_minimum",
                                "node_id": "node.manchester.aerospace.language.pte",
                                "test_type": "pte",
                                "total_min": "76",
                                "component_mins": {
                                    "listening": "70",
                                    "reading": "70",
                                    "speaking": "70",
                                    "writing": "70",
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
            "pack_ref": "pack.uk.manchester.msc_aerospace_engineering.2027.v1",
            "scope_snapshot_id": "scope.alpha.2027.v2",
            "scope_institution_ref": "institution.uk.manchester",
            "target_academic_year": ACADEMIC_YEAR,
            "program": {
                "program_ref": PROGRAM_REF,
                "official_name": "MSc Aerospace Engineering",
                "institution_name": "The University of Manchester",
                "region": "united_kingdom",
                "official_program_url": PROGRAM_URL,
                "registered_official_domain": "manchester.ac.uk",
                "official_domain_aliases": [],
                "degree_type": "taught_masters",
                "created_by": PREPARER,
                "creation_note": (
                    "第四阶段 8.7 航空字段隔离、低空课程门禁与目标学年分流验证的 "
                    "Manchester Aerospace Candidate-only Program。"
                ),
            },
            "reviewed_source_ids": all_source_ids,
            "evidence": evidence,
            "candidate": {
                "base_version_id": None,
                "fields": fields,
                "created_by": PREPARER,
                "creation_note": (
                    "第四阶段 8.7 Manchester Aerospace 2027 候选；Advanced Control "
                    "和 Bristol 阻塞项目未生成 Pack，2026 参考学费未进入 Registry。"
                ),
                "request_id": "request.phase4.batch8.7.manchester.aerospace.v1",
            },
            "review": {
                "prepared_by": PREPARER,
                "prepared_at": PREPARED_AT,
                "reviewed_by": REVIEWER,
                "reviewed_at": REVIEWED_AT,
                "review_note": (
                    "产品负责人确认 8.7 来源、分类、字段与逐项目分流；仅 Manchester "
                    "Aerospace 进入 Candidate-only 生产，低空门禁和目标学年阻塞项保持关闭。"
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
    AlphaProgramPackV1.model_validate(pack)
    OUTPUT_PATH.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"generated {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
