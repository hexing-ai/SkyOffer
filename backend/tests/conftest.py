from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "synthetic_profiles.json"


@pytest.fixture
def profile_data() -> dict:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return deepcopy(data["cross_discipline_missing_language"])


@pytest.fixture
def valid_model_payload() -> dict:
    return {
        "schema_version": "applicant_analysis_output.v1",
        "analysis_scope": "profile_only",
        "profile_summary": {
            "education": "华东示例理工大学自动化专业本科在读，预计 2027 年毕业，攻读工学学士。",
            "academic_metrics_raw": "原始成绩为 82.4/100，未进行任何换算。",
            "target_summary": "目标地区为香港和英国，关注人工智能与低空经济方向。",
        },
        "direction_evidence": [
            {
                "direction": "artificial_intelligence",
                "signals": ["已修读 Python 程序设计和机器学习导论。"],
                "gaps": ["尚未提供更完整的算法、概率统计及 AI 项目细节。"],
                "input_evidence_refs": ["core_courses[2]", "core_courses[4]"],
            },
            {
                "direction": "low_altitude_economy",
                "signals": ["无人机视觉项目涉及目标检测和飞行控制数据分析。"],
                "gaps": ["尚未说明项目中的个人职责、产出和飞行系统课程深度。"],
                "input_evidence_refs": [
                    "experiences[0].title",
                    "experiences[0].description",
                    "core_courses[3]",
                ],
            },
        ],
        "missing_information": [
            {
                "field": "language_scores",
                "why_it_matters": "后续检查具体项目语言要求时需要考试类型、总分和单项。",
                "requested_input": "请补充已取得或计划参加的语言考试及各项成绩。",
            }
        ],
        "consistency_flags": [],
        "next_questions": [
            "你是否已经参加 IELTS、TOEFL 或 PTE？",
            "无人机视觉项目中你具体负责哪些模块？",
            "是否修读概率统计、数据结构或算法课程？",
        ],
        "limitations": [
            "本分析未使用已核验院校项目数据。",
            "本分析未进行项目门槛、录取概率或录取承诺判断。",
        ],
    }
