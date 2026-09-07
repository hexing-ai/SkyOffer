from __future__ import annotations

import json
import logging
import platform
import statistics
import sys
import time

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.rules.evaluator import RequirementEngine
from backend.app.schemas.requirement_rules import (
    ApplicantEligibilityInput,
    RequirementRuleSet,
)


def build_fixture() -> tuple[ApplicantEligibilityInput, RequirementRuleSet]:
    profile = ApplicantEligibilityInput.model_validate(
        {
            "schema_version": "applicant_eligibility_input.v1",
            "profile_ref": "profile.synthetic.performance",
            "applicant_region": "china_mainland",
            "degree_level": "bachelor",
            "degree_status": "in_progress",
            "graduation_year": 2027,
            "degree_subject_tags": ["automation"],
            "institution_tags": ["china_mainland_recognized"],
            "academic_record": {"value": "82.4", "scale": "100"},
            "course_tags": [],
            "language_results": [],
            "work_experience_months": 0,
            "materials": {},
        }
    )
    requirements = []
    for requirement_index in range(100):
        children = [
            {
                "node_id": f"node.r{requirement_index:03d}.n{node_index:02d}",
                "operator": "numeric_min",
                "fact_path": "graduation_year",
                "minimum": 2027,
            }
            for node_index in range(49)
        ]
        requirements.append(
            {
                "requirement_id": f"requirement.perf.{requirement_index:03d}",
                "requirement_type": "degree",
                "is_hard": True,
                "rule": {
                    "node_id": f"node.r{requirement_index:03d}.root",
                    "operator": "all",
                    "children": children,
                },
                "evidence_fixture_ids": [f"evidence.perf.{requirement_index:03d}"],
                "display_text": "合成性能规则",
            }
        )
    rule_set = RequirementRuleSet.model_validate(
        {
            "schema_version": "requirement_rule_set.v1",
            "ruleset_id": "ruleset.synthetic.performance",
            "ruleset_version": "1.0.0",
            "engine_contract_version": "requirement_engine.v1",
            "synthetic_program_ref": "program.synthetic.performance",
            "requirements": requirements,
        }
    )
    return profile, rule_set


def percentile_95(samples: list[float]) -> float:
    return sorted(samples)[max(0, int(len(samples) * 0.95) - 1)]


def main() -> int:
    logging.disable(logging.CRITICAL)
    profile, rule_set = build_fixture()
    engine = RequirementEngine()
    engine.evaluate(profile, rule_set)
    core_samples = []
    for _ in range(30):
        started = time.perf_counter()
        engine.evaluate(profile, rule_set)
        core_samples.append((time.perf_counter() - started) * 1000)

    request = {
        "profile": profile.model_dump(mode="json"),
        "rule_set": rule_set.model_dump(mode="json"),
    }
    api_samples = []
    settings = Settings(_env_file=None, model_api_key=None, log_level="CRITICAL")
    with TestClient(create_app(settings, requirement_engine=engine)) as client:
        client.post("/api/v1/requirement-evaluations", json=request).raise_for_status()
        for _ in range(20):
            started = time.perf_counter()
            client.post("/api/v1/requirement-evaluations", json=request).raise_for_status()
            api_samples.append((time.perf_counter() - started) * 1000)

    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "engine_version": engine.version,
        "requirements": 100,
        "nodes_per_requirement": 50,
        "core_samples": len(core_samples),
        "core_p95_ms": round(percentile_95(core_samples), 3),
        "core_median_ms": round(statistics.median(core_samples), 3),
        "api_samples": len(api_samples),
        "api_p95_ms": round(percentile_95(api_samples), 3),
        "api_median_ms": round(statistics.median(api_samples), 3),
        "core_gate_ms": 100,
        "api_gate_ms": 300,
    }
    report["passed"] = (
        report["core_p95_ms"] <= report["core_gate_ms"]
        and report["api_p95_ms"] <= report["api_gate_ms"]
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
