from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.rules.canonical import content_hash
from backend.app.schemas.historical_reference import HistoricalReferenceDataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "alpha_v1"
    / "historical_references"
    / "historical_reference_2026_27.v1.json"
)
VERIFIED_AT = "2026-09-04T06:49:17Z"


def _source(program_ref: str, index: int, url: str, title: str, excerpt: str) -> dict:
    digest = content_hash(program_ref)[:10]
    normalized = excerpt.strip()
    return {
        "source_id": f"source.history.{digest}.{index}",
        "url": url,
        "page_title": title,
        "excerpt": normalized,
        "source_version": "2026/27 official page verified 2026-09-04",
        "verified_at": VERIFIED_AT,
        "snapshot_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }


def _node(program_ref: str, field_key: str, suffix: str, **payload) -> dict:
    digest = content_hash({"program_ref": program_ref, "field_key": field_key})[:10]
    return {"node_id": f"node.history.{digest}.{suffix}", **payload}


def _field(
    program_ref: str,
    field_key: str,
    display_text: str,
    rule: dict,
    source_ids: list[str],
) -> dict:
    digest = content_hash({"program_ref": program_ref, "field_key": field_key})[:10]
    requirement_type = {
        "requirements.degree": "degree",
        "requirements.academic": "academic",
        "requirements.subject": "subject",
        "requirements.prerequisite_courses": "course",
        "requirements.language": "language",
    }[field_key]
    return {
        "field_key": field_key,
        "display_text": display_text,
        "source_ids": source_ids,
        "requirement": {
            "requirement_id": f"requirement.history.{digest}",
            "requirement_type": requirement_type,
            "is_hard": True,
            "rule": rule,
            "evidence_fixture_ids": source_ids,
            "display_text": display_text[:500],
        },
    }


def _degree(program_ref: str, text: str, source_ids: list[str]) -> dict:
    key = "requirements.degree"
    return _field(
        program_ref,
        key,
        text,
        _node(
            program_ref,
            key,
            "degree",
            operator="enum_in",
            fact_path="degree_level",
            allowed_values=["bachelor"],
        ),
        source_ids,
    )


def _manual(program_ref: str, key: str, text: str, source_ids: list[str]) -> dict:
    return _field(
        program_ref,
        key,
        text,
        _node(
            program_ref,
            key,
            "manual",
            operator="manual_review",
            reason_code="OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
        ),
        source_ids,
    )


def _subject(program_ref: str, text: str, tags: list[str], source_ids: list[str]) -> dict:
    key = "requirements.subject"
    return _field(
        program_ref,
        key,
        text,
        _node(
            program_ref,
            key,
            "subject",
            operator="set_intersects",
            fact_path="degree_subject_tags",
            accepted_values=tags,
            minimum_matches=1,
        ),
        source_ids,
    )


def _courses(
    program_ref: str,
    text: str,
    groups: list[list[str]],
    source_ids: list[str],
) -> dict:
    key = "requirements.prerequisite_courses"
    children = [
        _node(
            program_ref,
            key,
            f"course{index}",
            operator="course_group",
            accepted_tags=tags,
            minimum_courses=1,
        )
        for index, tags in enumerate(groups, start=1)
    ]
    rule = children[0] if len(children) == 1 else _node(
        program_ref, key, "all", operator="all", children=children
    )
    return _field(program_ref, key, text, rule, source_ids)


def _language(
    program_ref: str,
    text: str,
    total: float,
    component: float,
    source_ids: list[str],
) -> dict:
    key = "requirements.language"
    return _field(
        program_ref,
        key,
        text,
        _node(
            program_ref,
            key,
            "ielts",
            operator="language_minimum",
            test_type="ielts",
            total_min=total,
            component_mins={
                "listening": component,
                "reading": component,
                "writing": component,
                "speaking": component,
            },
        ),
        source_ids,
    )


def _program(
    program_ref: str,
    sources: list[tuple[str, str, str]],
    field_builder,
    *,
    limitation_note: str | None = None,
) -> dict:
    built_sources = [
        _source(program_ref, index, *source)
        for index, source in enumerate(sources, start=1)
    ]
    source_ids = [item["source_id"] for item in built_sources]
    return {
        "program_ref": program_ref,
        "academic_year": "2026-27",
        "availability": "evaluable",
        "sources": built_sources,
        "fields": field_builder(source_ids),
        "limitation_note": limitation_note,
    }


def _programs() -> list[dict]:
    cs_tags = ["computer_science", "artificial_intelligence", "data_science"]
    engineering_tags = [
        "aerospace_engineering",
        "mechanical_engineering",
        "electronic_engineering",
        "automation",
    ]
    quantitative_tags = [
        *cs_tags,
        *engineering_tags,
    ]
    return [
        _program(
            "program.hk.hku.msc_computer_science",
            [(
                "https://master.cds.hku.hk/msccs/admission/application-details/",
                "MSc in Computer Science - Application details - HKU",
                "Programme Fee for 2026/27 Intake (For reference only). To be eligible, a candidate shall hold a Bachelor’s degree of HKU or a qualification of equivalent standard from a comparable institution. Applicants whose language of teaching and/or examination was not English must satisfy the University English language requirement.",
            )],
            lambda s: [
                _degree("program.hk.hku.msc_computer_science", "2026/27：须持有学士学位或同等学历。", s),
                _manual("program.hk.hku.msc_computer_science", "requirements.academic", "2026/27 官网未公布可直接编码的最低均分，需个案参考。", s),
                _manual("program.hk.hku.msc_computer_science", "requirements.language", "2026/27 要求满足 HKU 高等学位英语要求，但项目页未列出可直接编码分数。", s),
            ],
            limitation_note="2026/27 项目页未公布明确均分、专业范围或语言分数，历史参考仅覆盖学位层级。",
        ),
        _program(
            "program.uk.bristol.msc_aerospace_engineering",
            [
                (
                    "https://www.bristol.ac.uk/study/postgraduate/taught/msc-aerospace-engineering/",
                    "MSc Aerospace Engineering | Study at Bristol",
                    "September 2026. You will typically need an upper second-class honours degree or an international equivalent in Aerospace Engineering, or Mechanical Engineering. Other Engineering degrees require units in Aerodynamics, Aeronautics, and Aerospace Structures with 40% or above in each unit. English language profile E.",
                ),
                (
                    "https://www.bristol.ac.uk/study/language-requirements/profile-e/",
                    "Profile E | Study at Bristol",
                    "IELTS Academic: 6.5 overall with no score below 6.0.",
                ),
            ],
            lambda s: [
                _degree("program.uk.bristol.msc_aerospace_engineering", "2026/27：须持有学士学位或同等学历。", [s[0]]),
                _manual("program.uk.bristol.msc_aerospace_engineering", "requirements.academic", "2026/27：通常要求英国 2:1 或国际同等成绩。", [s[0]]),
                _subject("program.uk.bristol.msc_aerospace_engineering", "2026/27：航空工程或机械工程；其他工程背景须满足额外航空课程要求。", ["aerospace_engineering", "mechanical_engineering"], [s[0]]),
                _language("program.uk.bristol.msc_aerospace_engineering", "2026/27：IELTS 6.5，单项不低于 6.0。", 6.5, 6.0, [s[1]]),
            ],
            limitation_note="其他工程背景的三门航空课程条件需要人工逐项判断。",
        ),
        _program(
            "program.uk.bristol.msc_artificial_intelligence",
            [
                (
                    "https://www.bristol.ac.uk/study/postgraduate/taught/msc-artificial-intelligence/",
                    "MSc Artificial Intelligence | Study at Bristol",
                    "September 2026. A strong upper second-class honours degree (65% or higher) or international equivalent in Computer Science, Computing, Engineering, Architecture, Data Science, Mathematics, Statistics, Physics, Biology, Economics and other listed numerate subjects. Some Chemistry or joint honours applicants need mathematics/programming units at 60%. English language profile C.",
                ),
                (
                    "https://www.bristol.ac.uk/study/language-requirements/profile-c/",
                    "Profile C | Study at Bristol",
                    "IELTS Academic: 6.5 overall with 6.5 in all skills.",
                ),
            ],
            lambda s: [
                _degree("program.uk.bristol.msc_artificial_intelligence", "2026/27：须持有学士学位或同等学历。", [s[0]]),
                _manual("program.uk.bristol.msc_artificial_intelligence", "requirements.academic", "2026/27：通常要求强 2:1，英国口径为 65% 或以上；国际成绩需换算。", [s[0]]),
                _subject("program.uk.bristol.msc_artificial_intelligence", "2026/27：接受计算机、工程、数据、数学、统计、物理、经济等量化专业。", quantitative_tags, [s[0]]),
                _language("program.uk.bristol.msc_artificial_intelligence", "2026/27：IELTS 6.5，四项均不低于 6.5。", 6.5, 6.5, [s[1]]),
            ],
            limitation_note="部分化学、联合学位或非量化背景需按官网课程条件个案复核。",
        ),
        _program(
            "program.uk.edinburgh.msc_computer_science",
            [(
                "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science",
                "Computer Science MSc - Postgraduate taught programmes | Edinburgh",
                "These entry requirements are for the 2026-27 academic year. A UK 2:1 honours degree or international equivalent in informatics, artificial intelligence, cognitive science, computer science, econometrics, electrical engineering, mathematics, physics or another quantitative discipline. Programming is essential and 60 SCQF or 30 ECTS credits of mathematics are required. IELTS Academic total 7.0 with at least 6.5 in each component.",
            )],
            lambda s: [
                _degree("program.uk.edinburgh.msc_computer_science", "2026/27：须持有英国 2:1 学士学位或国际同等学历。", s),
                _manual("program.uk.edinburgh.msc_computer_science", "requirements.academic", "2026/27：最低 2:1，典型录取通常要求英国一等学位；中国成绩需按学校换算。", s),
                _subject("program.uk.edinburgh.msc_computer_science", "2026/27：接受计算机、AI、计量经济、电气、数学、物理及其他量化专业。", quantitative_tags, s),
                _courses("program.uk.edinburgh.msc_computer_science", "2026/27：必须有编程课程，并完成相当于 30 ECTS 的数学课程。", [["programming"], ["mathematics"]], s),
                _language("program.uk.edinburgh.msc_computer_science", "2026/27：IELTS 7.0，单项不低于 6.5。", 7.0, 6.5, s),
            ],
            limitation_note="数学学分数量和课程覆盖范围仍需根据成绩单人工确认。",
        ),
        _program(
            "program.uk.edinburgh.msc_artificial_intelligence",
            [(
                "https://study.ed.ac.uk/programmes/postgraduate-taught/107-artificial-intelligence",
                "Artificial Intelligence MSc - Postgraduate taught programmes | Edinburgh",
                "These entry requirements are for the 2026-27 academic year. A UK 2:1 honours degree or international equivalent in informatics, artificial intelligence, cognitive science, computer science, econometrics, electrical engineering, linguistics, mathematics, philosophy, physics or psychology. Programming is essential and 60 SCQF or 30 ECTS credits of mathematics are required. IELTS Academic total 7.0 with at least 6.5 in each component.",
            )],
            lambda s: [
                _degree("program.uk.edinburgh.msc_artificial_intelligence", "2026/27：须持有英国 2:1 学士学位或国际同等学历。", s),
                _manual("program.uk.edinburgh.msc_artificial_intelligence", "requirements.academic", "2026/27：最低 2:1，典型录取通常要求英国一等学位；中国成绩需按学校换算。", s),
                _subject("program.uk.edinburgh.msc_artificial_intelligence", "2026/27：接受 AI、计算机、计量经济、电气、数学、物理等相关专业。", quantitative_tags, s),
                _courses("program.uk.edinburgh.msc_artificial_intelligence", "2026/27：必须有编程课程，并完成相当于 30 ECTS 的数学课程。", [["programming"], ["mathematics"]], s),
                _language("program.uk.edinburgh.msc_artificial_intelligence", "2026/27：IELTS 7.0，单项不低于 6.5。", 7.0, 6.5, s),
            ],
            limitation_note="数学学分数量、概率知识和课程覆盖范围仍需根据成绩单人工确认。",
        ),
        _program(
            "program.uk.imperial.msc_computing",
            [(
                "https://www.imperial.ac.uk/study/courses/postgraduate-taught/computing/",
                "Computing MSc | Study | Imperial College London",
                "Applications are now closed for 2026 entry. First-class degree in any subject outside computing or computer science. Suitable for graduates of disciplines other than computing, this one-year programme is tailored towards those looking to add computing qualifications to their portfolio.",
            )],
            lambda s: [
                _degree("program.uk.imperial.msc_computing", "2026/27：须持有学士学位。", s),
                _manual("program.uk.imperial.msc_computing", "requirements.academic", "2026 entry：要求英国一等学位或同等水平。", s),
                _manual("program.uk.imperial.msc_computing", "requirements.subject", "2026 entry：仅面向非计算机或非计算机科学本科，当前规则需人工判断排除条件。", s),
            ],
            limitation_note="Imperial 当前自动访问受限，历史来源沿用 2026-09-03 已完成领域复核的官方页面摘录；语言门槛未写入。",
        ),
        _program(
            "program.uk.imperial.msc_artificial_intelligence",
            [(
                "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                "Artificial Intelligence MSc | Study | Imperial College London",
                "Applications are now closed for 2026 entry. First-Class Honours in Mathematics, Physics, Engineering or other degree with substantial Mathematics content. Aimed at mathematically-minded STEM graduates.",
            )],
            lambda s: [
                _degree("program.uk.imperial.msc_artificial_intelligence", "2026/27：须持有学士学位。", s),
                _manual("program.uk.imperial.msc_artificial_intelligence", "requirements.academic", "2026 entry：要求英国一等荣誉学位或同等水平。", s),
                _subject("program.uk.imperial.msc_artificial_intelligence", "2026 entry：数学、物理、工程或具有大量数学内容的其他专业；当前自动判断仅覆盖受控工程专业标签。", engineering_tags, s),
            ],
            limitation_note="Imperial 当前自动访问受限，历史来源沿用 2026-09-03 已完成领域复核的官方页面摘录；语言门槛未写入。",
        ),
        _program(
            "program.uk.imperial.msc_advanced_aeronautical_engineering",
            [(
                "https://www.imperial.ac.uk/study/courses/postgraduate-taught/advanced-aeronautical-engineering/",
                "Advanced Aeronautical Engineering MSc | Study | Imperial College London",
                "Applications are now closed for 2026 entry. 2:1, preferably First, in Aerospace or Mechanical Engineering with some experience of fluid and structural dynamics.",
            )],
            lambda s: [
                _degree("program.uk.imperial.msc_advanced_aeronautical_engineering", "2026/27：须持有学士学位。", s),
                _manual("program.uk.imperial.msc_advanced_aeronautical_engineering", "requirements.academic", "2026 entry：最低英国 2:1，偏好一等学位。", s),
                _subject("program.uk.imperial.msc_advanced_aeronautical_engineering", "2026 entry：航空航天或机械工程，并具备流体与结构动力学经验。", ["aerospace_engineering", "mechanical_engineering"], s),
            ],
            limitation_note="Imperial 当前自动访问受限，历史来源沿用 2026-09-03 已完成领域复核的官方页面摘录；语言门槛未写入。",
        ),
        _program(
            "program.uk.sheffield.msc_advanced_computer_science",
            [(
                "https://sheffield.ac.uk/postgraduate/taught/courses/2026/advanced-computer-science-msc",
                "Advanced Computer Science MSc | 2026 | Postgraduate",
                "2026-27 entry. Minimum 2:1 undergraduate honours degree in a relevant subject. Accepted subjects include Artificial Intelligence, Computer Engineering and Computer Science. IELTS 6.5 with 6.0 in each component.",
            )],
            lambda s: [
                _degree("program.uk.sheffield.msc_advanced_computer_science", "2026/27：须持有本科学位。", s),
                _manual("program.uk.sheffield.msc_advanced_computer_science", "requirements.academic", "2026/27：最低英国 2:1 或国际同等水平。", s),
                _subject("program.uk.sheffield.msc_advanced_computer_science", "2026/27：接受 AI、计算机工程、计算机科学等相关专业。", cs_tags, s),
                _language("program.uk.sheffield.msc_advanced_computer_science", "2026/27：IELTS 6.5，单项不低于 6.0。", 6.5, 6.0, s),
            ],
        ),
        _program(
            "program.uk.sheffield.msc_aerospace_engineering",
            [(
                "https://sheffield.ac.uk/postgraduate/taught/courses/2026/aerospace-engineering-msc",
                "Aerospace Engineering MSc | 2026 | Postgraduate",
                "2026-27 entry. Minimum 2:1 undergraduate honours degree in a relevant subject with relevant modules. Accepted subjects include Aerospace, Mechanical, Electrical, Civil, Computer Science, Control Systems and other engineering subjects. At least one Calculus, Linear Algebra or Mathematics module. IELTS 6.5 with 6.0 in each component.",
            )],
            lambda s: [
                _degree("program.uk.sheffield.msc_aerospace_engineering", "2026/27：须持有本科学位。", s),
                _manual("program.uk.sheffield.msc_aerospace_engineering", "requirements.academic", "2026/27：最低英国 2:1 或国际同等水平。", s),
                _subject("program.uk.sheffield.msc_aerospace_engineering", "2026/27：接受航空、机械、电气、土木、计算机、控制及其他工程专业。", [*engineering_tags, "computer_science"], s),
                _courses("program.uk.sheffield.msc_aerospace_engineering", "2026/27：至少修读一门微积分、线性代数或数学课程。", [["mathematics"]], s),
                _language("program.uk.sheffield.msc_aerospace_engineering", "2026/27：IELTS 6.5，单项不低于 6.0。", 6.5, 6.0, s),
            ],
        ),
        _program(
            "program.uk.sheffield.msc_artificial_intelligence",
            [(
                "https://sheffield.ac.uk/postgraduate/taught/courses/2026/artificial-intelligence-msc",
                "Artificial Intelligence MSc | 2026 | Postgraduate",
                "2026-27 entry. Minimum 2:1 undergraduate honours degree in a relevant subject. Accepted subjects include Artificial Intelligence, Chemistry, Computer Science, Economics, Mathematics, Physics and any Engineering subject. IELTS 6.5 with 6.0 in each component.",
            )],
            lambda s: [
                _degree("program.uk.sheffield.msc_artificial_intelligence", "2026/27：须持有本科学位。", s),
                _manual("program.uk.sheffield.msc_artificial_intelligence", "requirements.academic", "2026/27：最低英国 2:1 或国际同等水平。", s),
                _subject("program.uk.sheffield.msc_artificial_intelligence", "2026/27：接受 AI、化学、计算机、经济、数学、物理及工程专业。", quantitative_tags, s),
                _language("program.uk.sheffield.msc_artificial_intelligence", "2026/27：IELTS 6.5，单项不低于 6.0。", 6.5, 6.0, s),
            ],
        ),
        _program(
            "program.uk.sheffield.msc_robotics",
            [(
                "https://sheffield.ac.uk/postgraduate/taught/courses/2026/robotics-msc",
                "Robotics MSc | 2026 | Postgraduate",
                "2026-27 entry. Minimum 2:1 undergraduate honours degree in Engineering, Mathematics or Physics with relevant modules. At least one Mathematics module and one module in Further Mathematics, Physics, Probability and Statistics, or Programming. IELTS 6.5 with 6.0 in each component.",
            )],
            lambda s: [
                _degree("program.uk.sheffield.msc_robotics", "2026/27：须持有本科学位。", s),
                _manual("program.uk.sheffield.msc_robotics", "requirements.academic", "2026/27：最低英国 2:1 或国际同等水平。", s),
                _subject("program.uk.sheffield.msc_robotics", "2026/27：接受工程、数学或物理专业；当前自动判断仅覆盖受控工程专业标签。", engineering_tags, s),
                _courses("program.uk.sheffield.msc_robotics", "2026/27：至少一门数学课，并具备进阶数学、物理、概率统计或编程课程；当前自动判断覆盖数学、统计与编程标签。", [["mathematics"], ["statistics", "programming"]], s),
                _language("program.uk.sheffield.msc_robotics", "2026/27：IELTS 6.5，单项不低于 6.0。", 6.5, 6.0, s),
            ],
        ),
        _program(
            "program.uk.ucl.msc_computer_science",
            [(
                "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/computer-science-msc",
                "Computer Science MSc | Prospective Students Graduate - UCL",
                "Programme starts September 2026. A minimum upper second-class UK Bachelor's degree or international equivalent in a subject other than computer science or information technology. Applicants must demonstrate mathematics at least to A-level standard and analytical ability.",
            )],
            lambda s: [
                _degree("program.uk.ucl.msc_computer_science", "2026/27：须持有英国本科 2:1 或国际同等学历。", s),
                _manual("program.uk.ucl.msc_computer_science", "requirements.academic", "2026/27：最低英国 2:1；国际成绩需按 UCL 口径换算。", s),
                _manual("program.uk.ucl.msc_computer_science", "requirements.subject", "2026/27：仅面向非计算机科学或非信息技术本科，排除条件需人工判断。", s),
                _courses("program.uk.ucl.msc_computer_science", "2026/27：须证明至少达到 A-level 水平的数学能力。", [["mathematics"]], s),
            ],
            limitation_note="UCL 当前自动访问受限，历史来源沿用 2026-09-03 已完成领域复核的官方页面摘录；语言门槛未写入。",
        ),
        _program(
            "program.uk.ucl.msc_robotics_artificial_intelligence",
            [(
                "https://www.ucl.ac.uk/prospective-students/graduate/taught-degrees/robotics-and-artificial-intelligence-msc",
                "Robotics and Artificial Intelligence MSc | Prospective Students Graduate - UCL",
                "Programme starts September 2026. A minimum upper second-class UK Bachelor's degree or international equivalent in a highly quantitative subject such as computer science, mathematics, electrical or electronic engineering, or physical sciences. Applicants need calculus, linear algebra, probability and programming experience in C/C++, Java, Python or Matlab.",
            )],
            lambda s: [
                _degree("program.uk.ucl.msc_robotics_artificial_intelligence", "2026/27：须持有英国本科 2:1 或国际同等学历。", s),
                _manual("program.uk.ucl.msc_robotics_artificial_intelligence", "requirements.academic", "2026/27：最低英国 2:1；国际成绩需按 UCL 口径换算。", s),
                _subject("program.uk.ucl.msc_robotics_artificial_intelligence", "2026/27：要求计算机、数学、电气电子、物理科学等高度量化专业；当前自动判断覆盖受控计算机、AI 与电子工程标签。", ["computer_science", "artificial_intelligence", "electronic_engineering"], s),
                _courses("program.uk.ucl.msc_robotics_artificial_intelligence", "2026/27：需要微积分、线性代数、概率以及 C/C++、Java、Python 或 Matlab 编程经验。", [["mathematics"], ["statistics"], ["programming"]], s),
            ],
            limitation_note="UCL 当前自动访问受限，历史来源沿用 2026-09-03 已完成领域复核的官方页面摘录；语言门槛未写入。",
        ),
    ]


def build_dataset() -> HistoricalReferenceDataset:
    return HistoricalReferenceDataset.model_validate(
        {
            "schema_version": "historical_reference_dataset.v1",
            "dataset_id": "dataset.historical_reference.2026-27.v1",
            "academic_year": "2026-27",
            "generated_at": datetime(2026, 9, 4, 6, 49, 17, tzinfo=UTC),
            "public_publishable": False,
            "programs": _programs(),
        }
    )


def main() -> int:
    dataset = build_dataset()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(dataset.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
