from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from backend.app.rules.canonical import content_hash
from backend.app.schemas.field_registry import load_program_field_registry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
OUTPUT_DIR = DATA_ROOT / "candidate_batches"
OUTPUT_PATH = OUTPUT_DIR / "coverage_2027_batch_v1.json"

TARGET_YEAR = "2027-28"
CAPTURED_AT = "2026-09-04T12:00:00+08:00"
REVIEW_DUE_AT = "2026-10-04T12:00:00+08:00"
EXPIRES_AT = "2026-12-03T12:00:00+08:00"
BASE_DATASET_ID = "dataset.internal_alpha.2027.v1"
BASE_MANIFEST_SHA256 = "b10c4f43c1242864415d720d4dbe1db728a9d240a996df4d60f72bb3ed584938"
BASE_PROGRAM_COUNT = 6


def _source(
    *,
    source_id: str,
    url: str,
    title: str,
    excerpt: str,
    role: str = "program",
) -> dict:
    return {
        "source_id": source_id,
        "url": url,
        "official_domain": urlsplit(url).hostname,
        "page_title": title,
        "excerpt": excerpt,
        "snapshot_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "source_version": (
            "Official page captured 2026-09-04 for candidate generation; "
            "2027-28 admissions facts are not inferred from older-cycle content"
        ),
        "captured_at": CAPTURED_AT,
        "review_due_at": REVIEW_DUE_AT,
        "expires_at": EXPIRES_AT,
        "capture_method": "automated_web_candidate",
        "reviewed_source_role": role,
    }


PROGRAMS = [
    {
        "program_ref": "program.hk.hku.msc_artificial_intelligence",
        "pack_ref": "pack.hk.hku.msc_artificial_intelligence.2027.v1",
        "institution_ref": "institution.hk.hku",
        "region": "hong_kong",
        "official_name": "Master of Science in Artificial Intelligence",
        "official_url": "https://www.mscai.hku.hk/",
        "primary_direction": "artificial_intelligence",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.hku.mscai.program.20260904.v1",
                url="https://www.mscai.hku.hk/",
                title="The University of Hong Kong - Master of Science in Artificial Intelligence",
                excerpt=(
                    "Master of Science in Artificial Intelligence\n"
                    "About MSc(AI)\n"
                    "In today’s technologically advanced era, the indispensability of artificial intelligence (AI) in our daily lives is undeniable."
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.imperial.msc_computing",
        "pack_ref": "pack.uk.imperial.msc_computing.2027.v1",
        "institution_ref": "institution.uk.imperial",
        "region": "united_kingdom",
        "official_name": "Computing MSc",
        "official_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/computing/",
        "primary_direction": "computer_science",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.imperial.computing.program.20260904.v1",
                url="https://www.imperial.ac.uk/study/courses/postgraduate-taught/computing/",
                title="Computing MSc | Study | Imperial College London",
                excerpt=(
                    "Computing MSc\nApplications are now closed for 2026 entry.\n"
                    "Start date — September 2026\nPrinciples and Practice of Programming\n"
                    "Computer Systems\nSoftware Systems Engineering"
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.imperial.msc_artificial_intelligence",
        "pack_ref": "pack.uk.imperial.msc_artificial_intelligence.2027.v1",
        "institution_ref": "institution.uk.imperial",
        "region": "united_kingdom",
        "official_name": "Artificial Intelligence MSc",
        "official_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
        "primary_direction": "artificial_intelligence",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.imperial.ai.program.20260904.v1",
                url="https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                title="Artificial Intelligence MSc | Study | Imperial College London",
                excerpt=(
                    "Artificial Intelligence MSc\nApplications are now closed for 2026 entry.\n"
                    "Start date — September 2026\nIntroduction to Machine Learning\n"
                    "Python Programming\nSoftware Engineering Group Project"
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.imperial.msc_advanced_aeronautical_engineering",
        "pack_ref": "pack.uk.imperial.msc_advanced_aeronautical_engineering.2027.v1",
        "institution_ref": "institution.uk.imperial",
        "region": "united_kingdom",
        "official_name": "Advanced Aeronautical Engineering MSc",
        "official_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/advanced-aeronautical-engineering/",
        "primary_direction": "aerospace_engineering",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.imperial.advanced_aero.program.20260904.v1",
                url="https://www.imperial.ac.uk/study/courses/postgraduate-taught/advanced-aeronautical-engineering/",
                title="Advanced Aeronautical Engineering MSc | Study | Imperial College London",
                excerpt=(
                    "Advanced Aeronautical Engineering MSc\n"
                    "Applications are now closed for 2026 entry.\nStart date — September 2026"
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.ucl.msc_computer_science",
        "pack_ref": "pack.uk.ucl.msc_computer_science.2027.v1",
        "institution_ref": "institution.uk.ucl",
        "region": "united_kingdom",
        "official_name": "Computer Science MSc",
        "official_url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/computer-science-msc",
        "primary_direction": "computer_science",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.ucl.computer_science.program.20260904.v1",
                url="https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/computer-science-msc",
                title="Computer Science MSc | Prospective Students Graduate - UCL – University College London",
                excerpt=(
                    "Computer Science MSc\nProgramme starts — September 2026\n"
                    "UK tuition fees (2026/27)\nIntroductory Programming\nApp Engineering\n"
                    "Computer Architecture and Operating Systems\nAlgorithmics\nDatabase Fundamentals"
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.ucl.msc_robotics_artificial_intelligence",
        "pack_ref": "pack.uk.ucl.msc_robotics_artificial_intelligence.2027.v1",
        "institution_ref": "institution.uk.ucl",
        "region": "united_kingdom",
        "official_name": "Robotics and Artificial Intelligence MSc",
        "official_url": "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/robotics-and-artificial-intelligence-msc",
        "primary_direction": "low_altitude_economy",
        "secondary_directions": ["artificial_intelligence"],
        "low_altitude_basis": {
            "inclusion_basis": "explicit_program_focus",
            "rationale_zh": "项目聚焦机器人与自主系统，且官方课程明确包含空中机器人课程；仅确认方向相关性，不沿用 2026 周期招生门槛。",
            "courses": [
                {
                    "course_name": "Aerial Robotics: Fundamentals to Practice in Real-World Environments",
                    "course_type": "elective",
                    "subtag": "unmanned_aircraft_systems",
                    "source_id": "source.candidate.ucl.robotics.curriculum.20260904.v1",
                }
            ],
        },
        "sources": [
            _source(
                source_id="source.candidate.ucl.robotics.program.20260904.v1",
                url="https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/robotics-and-artificial-intelligence-msc",
                title="Robotics and Artificial Intelligence MSc | Prospective Students Graduate - UCL – University College London",
                excerpt=(
                    "Robotics and Artificial Intelligence MSc\n"
                    "This Master's combines Computer Science, AI and Robotics, and Mechatronics, blending theory with hands-on experience.\n"
                    "Programme starts — September 2026\nUK tuition fees (2026/27)"
                ),
            ),
            _source(
                source_id="source.candidate.ucl.robotics.curriculum.20260904.v1",
                url="https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/robotics-and-artificial-intelligence-msc",
                title="Robotics and Artificial Intelligence MSc | Prospective Students Graduate - UCL – University College London",
                excerpt=(
                    "Optional modules\n"
                    "Aerial Robotics: Fundamentals to Practice in Real-World Environments"
                ),
                role="curriculum",
            ),
        ],
    },
    {
        "program_ref": "program.uk.edinburgh.msc_computer_science",
        "pack_ref": "pack.uk.edinburgh.msc_computer_science.2027.v1",
        "institution_ref": "institution.uk.edinburgh",
        "region": "united_kingdom",
        "official_name": "Computer Science MSc",
        "official_url": "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science",
        "primary_direction": "computer_science",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.edinburgh.computer_science.program.20260904.v1",
                url="https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science",
                title="Computer Science MSc - Postgraduate taught programmes | The University of Edinburgh",
                excerpt=(
                    "Computer Science MSc\nMSc | 1 year | Start date: September 2026\n"
                    "These entry requirements are for the 2026-27 academic year and requirements for future academic years may differ. "
                    "Entry requirements for the 2027-28 academic year will be published on 1 Oct 2026."
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.edinburgh.msc_artificial_intelligence",
        "pack_ref": "pack.uk.edinburgh.msc_artificial_intelligence.2027.v1",
        "institution_ref": "institution.uk.edinburgh",
        "region": "united_kingdom",
        "official_name": "Artificial Intelligence MSc",
        "official_url": "https://study.ed.ac.uk/programmes/postgraduate-taught/107-artificial-intelligence",
        "primary_direction": "artificial_intelligence",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.edinburgh.ai.program.20260904.v1",
                url="https://study.ed.ac.uk/programmes/postgraduate-taught/107-artificial-intelligence",
                title="Artificial Intelligence MSc - Postgraduate taught programmes | The University of Edinburgh",
                excerpt=(
                    "Artificial Intelligence MSc\nMSc | 1 year | Start date: September 2026\n"
                    "These entry requirements are for the 2026-27 academic year and requirements for future academic years may differ. "
                    "Entry requirements for the 2027-28 academic year will be published on 1 Oct 2026."
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.bristol.msc_aerospace_engineering",
        "pack_ref": "pack.uk.bristol.msc_aerospace_engineering.2027.v1",
        "institution_ref": "institution.uk.bristol",
        "region": "united_kingdom",
        "official_name": "MSc Aerospace Engineering",
        "official_url": "https://www.bristol.ac.uk/study/postgraduate/taught/msc-aerospace-engineering/",
        "primary_direction": "aerospace_engineering",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.bristol.aerospace.program.20260904.v1",
                url="https://www.bristol.ac.uk/study/postgraduate/taught/msc-aerospace-engineering/",
                title="MSc Aerospace Engineering | Study at Bristol | University of Bristol",
                excerpt=(
                    "MSc Aerospace Engineering\nStart date\nSeptember 2026\n"
                    "The MSc Aerospace Engineering programme is an advanced degree covering a broad range of aerospace subjects."
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.sheffield.msc_aerospace_engineering",
        "pack_ref": "pack.uk.sheffield.msc_aerospace_engineering.2027.v1",
        "institution_ref": "institution.uk.sheffield",
        "region": "united_kingdom",
        "official_name": "Aerospace Engineering MSc",
        "official_url": "https://sheffield.ac.uk/postgraduate/taught/courses/2026/aerospace-engineering-msc",
        "primary_direction": "aerospace_engineering",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.sheffield.aerospace.program.20260904.v1",
                url="https://sheffield.ac.uk/postgraduate/taught/courses/2026/aerospace-engineering-msc",
                title="Aerospace Engineering MSc | 2026 | Postgraduate",
                excerpt=(
                    "Aerospace Engineering MSc\n2026-27 entry\nStart date\nSeptember 2026\n"
                    "For students converting to aerospace engineering, you will study a series of foundational core modules designed to ensure you develop a strong aerospace understanding."
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.sheffield.msc_robotics",
        "pack_ref": "pack.uk.sheffield.msc_robotics.2027.v1",
        "institution_ref": "institution.uk.sheffield",
        "region": "united_kingdom",
        "official_name": "Robotics MSc",
        "official_url": "https://sheffield.ac.uk/postgraduate/taught/courses/2026/robotics-msc",
        "primary_direction": "low_altitude_economy",
        "secondary_directions": ["artificial_intelligence"],
        "low_altitude_basis": {
            "inclusion_basis": "curriculum_based",
            "rationale_zh": "官方核心课程同时覆盖自主系统中的机器视觉与无人航空系统，可作为低空自主系统方向候选；2027/28 课程仍待重新核验。",
            "courses": [
                {
                    "course_name": "Machine Vision for Robotics",
                    "course_type": "core",
                    "subtag": "airborne_sensing_navigation_communications",
                    "source_id": "source.candidate.sheffield.robotics.machine_vision.20260904.v1",
                },
                {
                    "course_name": "Mobile Robotics and Autonomous Systems",
                    "course_type": "core",
                    "subtag": "unmanned_aircraft_systems",
                    "source_id": "source.candidate.sheffield.robotics.mobile_systems.20260904.v1",
                },
            ],
        },
        "sources": [
            _source(
                source_id="source.candidate.sheffield.robotics.program.20260904.v1",
                url="https://sheffield.ac.uk/postgraduate/taught/courses/2026/robotics-msc",
                title="Robotics MSc | 2026 | Postgraduate",
                excerpt=(
                    "Robotics MSc\n2026-27 entry\nBecome an expert in robotics and autonomous systems, with the skills to join the next generation of engineers. "
                    "You’ll learn about machine and artificial intelligence (AI), robotic sensing and perception, control and planning and robotic devices and systems."
                ),
            ),
            _source(
                source_id="source.candidate.sheffield.robotics.machine_vision.20260904.v1",
                url="https://sheffield.ac.uk/postgraduate/taught/courses/2026/robotics-msc",
                title="Robotics MSc | 2026 | Postgraduate",
                excerpt=(
                    "Core modules:\nMachine Vision for Robotics\nThe module gives knowledge of machine vision methods for a broad range of applications. "
                    "It introduces you to image and video processing models and methods and provides you with skills on how to embed them in autonomous systems."
                ),
                role="curriculum",
            ),
            _source(
                source_id="source.candidate.sheffield.robotics.mobile_systems.20260904.v1",
                url="https://sheffield.ac.uk/postgraduate/taught/courses/2026/robotics-msc",
                title="Robotics MSc | 2026 | Postgraduate",
                excerpt=(
                    "Core modules:\nMobile Robotics and Autonomous Systems\n"
                    "From advanced manufacturing and surgical robots to unmanned aerial systems and driverless cars, this exciting area is presenting increasing technological challenges."
                ),
                role="curriculum",
            ),
        ],
    },
    {
        "program_ref": "program.uk.sheffield.msc_artificial_intelligence",
        "pack_ref": "pack.uk.sheffield.msc_artificial_intelligence.2027.v1",
        "institution_ref": "institution.uk.sheffield",
        "region": "united_kingdom",
        "official_name": "Artificial Intelligence MSc",
        "official_url": "https://sheffield.ac.uk/postgraduate/taught/courses/2026/artificial-intelligence-msc",
        "primary_direction": "artificial_intelligence",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.sheffield.ai.program.20260904.v1",
                url="https://sheffield.ac.uk/postgraduate/taught/courses/2026/artificial-intelligence-msc",
                title="Artificial Intelligence MSc | 2026 | Postgraduate",
                excerpt=(
                    "Artificial Intelligence MSc\n2026-27 entry\nStart date\nSeptember 2026\n"
                    "This MSc will teach you the theoretical aspects of AI and provide the practical skills needed to work with big data sets for solving a wide range of real-world problems."
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.bristol.msc_artificial_intelligence",
        "pack_ref": "pack.uk.bristol.msc_artificial_intelligence.2027.v1",
        "institution_ref": "institution.uk.bristol",
        "region": "united_kingdom",
        "official_name": "MSc Artificial Intelligence",
        "official_url": "https://www.bristol.ac.uk/study/postgraduate/taught/msc-artificial-intelligence/",
        "primary_direction": "artificial_intelligence",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.bristol.ai.program.20260904.v1",
                url="https://www.bristol.ac.uk/study/postgraduate/taught/msc-artificial-intelligence/",
                title="MSc Artificial Intelligence | Study at Bristol | University of Bristol",
                excerpt=(
                    "MSc Artificial Intelligence\nArtificial Intelligence\nStart date\nSeptember 2026\n"
                    "The MSc in Artificial Intelligence at the University of Bristol is a rigorous, research- and industry-informed programme designed for graduates from numerate disciplines."
                ),
            )
        ],
    },
    {
        "program_ref": "program.uk.sheffield.msc_advanced_computer_science",
        "pack_ref": "pack.uk.sheffield.msc_advanced_computer_science.2027.v1",
        "institution_ref": "institution.uk.sheffield",
        "region": "united_kingdom",
        "official_name": "Advanced Computer Science MSc",
        "official_url": "https://sheffield.ac.uk/postgraduate/taught/courses/2026/advanced-computer-science-msc",
        "primary_direction": "computer_science",
        "secondary_directions": [],
        "sources": [
            _source(
                source_id="source.candidate.sheffield.advanced_cs.program.20260904.v1",
                url="https://sheffield.ac.uk/postgraduate/taught/courses/2026/advanced-computer-science-msc",
                title="Advanced Computer Science MSc | 2026 | Postgraduate",
                excerpt=(
                    "Advanced Computer Science MSc\n2026-27 entry\nStart date\nSeptember 2026\n"
                    "Our MSc in Advanced Computer Science offers a variety of modules, including software engineering, machine learning, and human-computer interaction."
                ),
            )
        ],
    },
]


def _field_proposals(program: dict) -> list[dict]:
    registry = load_program_field_registry()
    source_ids = [item["source_id"] for item in program["sources"]]
    fields: list[dict] = []
    for definition in registry.fields:
        key = definition.field_key
        if key == "taxonomy.low_altitude_basis":
            if program.get("low_altitude_basis") is None:
                continue
            status = "confirmed"
            value = program["low_altitude_basis"]
        elif key == "catalog.degree_type":
            status = "confirmed"
            value = {"degree_type": "taught_masters"}
        elif key == "taxonomy.primary_direction":
            status = "confirmed"
            value = {"direction": program["primary_direction"]}
        elif key == "taxonomy.secondary_directions":
            status = "confirmed"
            value = {"directions": program["secondary_directions"]}
        elif key in {"catalog.department", "catalog.duration"}:
            status = "manual_review"
            value = None
        else:
            status = "not_yet_published"
            value = None
        fields.append(
            {
                "field_key": key,
                "is_critical": definition.is_critical,
                "proposed_coverage_status": status,
                "proposed_value": value,
                "source_ids": source_ids,
                "reason_code": (
                    None if status == "confirmed" else "OFFICIAL_RULE_NOT_PUBLISHED"
                ),
                "review_note": (
                    "2027/28 目标周期招生事实尚未在本批官方来源中发布或完成核验；"
                    "不沿用 2026/27 数值、日期或门槛。"
                    if status != "confirmed"
                    else None
                ),
            }
        )
    return fields


def build_batch() -> dict:
    candidates = []
    for raw in PROGRAMS:
        program = dict(raw)
        program["degree_type"] = "taught_masters"
        program["target_academic_year"] = TARGET_YEAR
        program["target_year_status"] = "official_2027_28_rules_pending"
        program["field_proposals"] = _field_proposals(program)
        program["high_risk_field_keys"] = sorted(
            field["field_key"]
            for field in program["field_proposals"]
            if field["is_critical"]
            and field["proposed_coverage_status"] != "confirmed"
        )
        program["exception_field_keys"] = sorted(
            field["field_key"]
            for field in program["field_proposals"]
            if field["proposed_coverage_status"] != "confirmed"
        )
        candidates.append(program)

    batch = {
        "schema_version": "internal_alpha_candidate_batch.v1",
        "batch_id": "candidate_batch.coverage.2027.20260904.v1",
        "lifecycle_state": "auto_quality_gated_pending_batch_domain_review",
        "target_academic_year": TARGET_YEAR,
        "public_publishable": False,
        "source_scope_snapshot_id": "scope.alpha.2027.v2",
        # These values freeze the reviewed input baseline. They must not drift when
        # the approved additions are later materialized into a newer manifest.
        "base_dataset_id": BASE_DATASET_ID,
        "base_manifest_sha256": BASE_MANIFEST_SHA256,
        "base_program_count": BASE_PROGRAM_COUNT,
        "candidate_addition_count": len(candidates),
        "projected_internal_program_count": BASE_PROGRAM_COUNT + len(candidates),
        "generated_at": CAPTURED_AT,
        "generated_by": "actor.data_preparer.codex",
        "capture_policy": "automated_candidate_only_no_2026_to_2027_fact_migration",
        "release_requires": "single_batch_domain_review",
        "replacement_diff": [
            {
                "removed_program_ref": "program.uk.manchester.msc_advanced_control_systems_engineering",
                "reason": "low_altitude_course_evidence_gate_failed",
                "added_program_ref": "program.uk.bristol.msc_artificial_intelligence",
            },
            {
                "removed_program_ref": "program.uk.bristol.msc_aerial_robotics",
                "reason": "qualifying_course_evidence_unavailable",
                "added_program_ref": "program.uk.sheffield.msc_advanced_computer_science",
            },
        ],
        "deferred_programs": [
            {
                "program_ref": "program.hk.cuhk.msc_computer_science",
                "reason": "official_page_unreachable_or_redirect_not_verified",
            },
            {
                "program_ref": "program.hk.polyu.msc_artificial_intelligence_big_data_computing",
                "reason": "frozen_official_url_returns_404",
            },
            {
                "program_ref": "program.hk.polyu.msc_information_technology",
                "reason": "frozen_official_url_returns_404",
            },
            {
                "program_ref": "program.hk.hkbu.msc_ai_digital_media",
                "reason": "official_page_unreachable",
            },
        ],
        "candidates": candidates,
        "batch_canonical_sha256": "0" * 64,
    }
    batch["batch_canonical_sha256"] = content_hash(
        {key: value for key, value in batch.items() if key != "batch_canonical_sha256"}
    )
    return batch


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch = build_batch()
    OUTPUT_PATH.write_text(
        json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)),
                "candidate_additions": batch["candidate_addition_count"],
                "projected_program_count": batch["projected_internal_program_count"],
                "batch_canonical_sha256": batch["batch_canonical_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
