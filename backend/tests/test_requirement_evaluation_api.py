from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.tests.test_requirement_engine import BASE_PROFILE


BASE_RULE_SET = {
    "schema_version": "requirement_rule_set.v1",
    "ruleset_id": "ruleset.synthetic.api",
    "ruleset_version": "1.0.0",
    "engine_contract_version": "requirement_engine.v1",
    "synthetic_program_ref": "program.synthetic.api",
    "requirements": [
        {
            "requirement_id": "requirement.academic",
            "requirement_type": "academic",
            "is_hard": True,
            "rule": {
                "node_id": "node.academic",
                "operator": "numeric_min",
                "fact_path": "academic_record.value",
                "minimum": "80",
                "scale": "100",
            },
            "evidence_fixture_ids": ["evidence.synthetic.api"],
            "display_text": "合成百分制均分不低于 80",
        }
    ],
}


def request_body() -> dict:
    return {
        "profile": deepcopy(BASE_PROFILE),
        "rule_set": deepcopy(BASE_RULE_SET),
    }


def build_client() -> TestClient:
    settings = Settings(_env_file=None, model_api_key=None)
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_requirement_evaluation_api_returns_trace_and_request_id() -> None:
    with build_client() as client:
        response = client.post("/api/v1/requirement-evaluations", json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["overall_hard_requirement_status"] == "met"
    assert body["requirement_results"][0]["trace"]["reason_code"] == (
        "VALUE_AT_OR_ABOVE_MIN"
    )
    assert len(body["evaluation_id"]) == 64
    assert body["request_id"].startswith("req_")
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert "MODEL_API_KEY" not in response.text


def test_api_core_payload_is_repeatable() -> None:
    with build_client() as client:
        first = client.post("/api/v1/requirement-evaluations", json=request_body()).json()
        second = client.post("/api/v1/requirement-evaluations", json=request_body()).json()
    for runtime_field in ("request_id", "duration_ms"):
        first.pop(runtime_field)
        second.pop(runtime_field)
    assert first == second


def test_invalid_profile_uses_phase_two_input_error() -> None:
    payload = request_body()
    payload["profile"]["email"] = "synthetic@example.com"
    with build_client() as client:
        response = client.post("/api/v1/requirement-evaluations", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_VALIDATION_FAILED"
    assert "synthetic@example.com" not in response.text


def test_unknown_fact_path_is_rule_invalid() -> None:
    payload = request_body()
    payload["rule_set"]["requirements"][0]["rule"]["fact_path"] = "secret.path"
    with build_client() as client:
        response = client.post("/api/v1/requirement-evaluations", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RULE_INVALID"


def test_unknown_rule_schema_version_is_explicit() -> None:
    payload = request_body()
    payload["rule_set"]["schema_version"] = "requirement_rule_set.v999"
    with build_client() as client:
        response = client.post("/api/v1/requirement-evaluations", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VERSION_UNSUPPORTED"


def test_unknown_operator_is_rule_validation_failure() -> None:
    payload = request_body()
    payload["rule_set"]["requirements"][0]["rule"]["operator"] = "python_eval"
    with build_client() as client:
        response = client.post("/api/v1/requirement-evaluations", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RULE_VALIDATION_FAILED"
    assert "traceback" not in response.text.lower()


def test_phase_two_page_is_available_and_has_fixed_boundary() -> None:
    with build_client() as client:
        response = client.get("/phase2")
    assert response.status_code == 200
    assert "第二阶段验收" in response.text
    assert "不调用 DeepSeek" in response.text
    assert "恰好等于 80/100" in response.text
    assert "未知 operator 必须安全拒绝" in response.text
    assert "RULE_VALIDATION_FAILED" in response.text
    assert "正式金标 v0.1.0" in response.text
    assert "150 / 150" in response.text
    assert "录取概率" not in response.text
    assert "MODEL_API_KEY" not in response.text
