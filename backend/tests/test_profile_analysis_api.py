from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.model_client import ModelResponse, ModelUsage
from backend.app.services.profile_analysis import ProfileAnalysisService


class StaticModelClient:
    def __init__(self, payload: dict):
        self.payload = payload

    async def complete(self, messages: list[dict[str, str]]) -> ModelResponse:
        return ModelResponse(
            content=json.dumps(self.payload, ensure_ascii=False),
            model_name="deepseek-chat",
            usage=ModelUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        )


def build_client(payload: dict, *, key: str = "test-key") -> TestClient:
    settings = Settings(_env_file=None, model_api_key=key or None)
    service = ProfileAnalysisService(settings, StaticModelClient(payload))
    return TestClient(create_app(settings, service), raise_server_exceptions=False)


def test_health_does_not_expose_secret(valid_model_payload: dict) -> None:
    with build_client(valid_model_payload) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_configuration": "ready"}
    assert "test-key" not in response.text


def test_profile_analysis_api_returns_contract(
    profile_data: dict, valid_model_payload: dict
) -> None:
    with build_client(valid_model_payload) as client:
        response = client.post("/api/v1/profile-analysis", json=profile_data)
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_scope"] == "profile_only"
    assert body["meta"]["request_id"].startswith("req_")
    assert response.headers["X-Request-ID"] == body["meta"]["request_id"]


def test_invalid_input_uses_unified_error(
    profile_data: dict, valid_model_payload: dict
) -> None:
    profile_data["grade_value"] = 101
    with build_client(valid_model_payload) as client:
        response = client.post("/api/v1/profile-analysis", json=profile_data)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INPUT_INVALID"
    assert error["request_id"].startswith("req_")
    assert "traceback" not in response.text.lower()


def test_extra_personal_field_is_rejected(
    profile_data: dict, valid_model_payload: dict
) -> None:
    profile_data["email"] = "synthetic@example.com"
    with build_client(valid_model_payload) as client:
        response = client.post("/api/v1/profile-analysis", json=profile_data)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INPUT_INVALID"


def test_phase_one_page_is_available(valid_model_payload: dict) -> None:
    with build_client(valid_model_payload) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "第一阶段验收" in response.text
    assert "MODEL_API_KEY" not in response.text
