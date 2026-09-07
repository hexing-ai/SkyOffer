from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest

from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.schemas.profile_analysis import ApplicantAnalysisInput
from backend.app.services.model_client import (
    ModelClientError,
    ModelResponse,
    ModelUsage,
)
from backend.app.services.profile_analysis import ProfileAnalysisService


class FakeModelClient:
    def __init__(self, responses: list[ModelResponse | Exception]):
        self.responses = list(responses)
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]]) -> ModelResponse:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def model_response(payload: dict, *, fenced: bool = False) -> ModelResponse:
    content = json.dumps(payload, ensure_ascii=False)
    if fenced:
        content = f"```json\n{content}\n```"
    return ModelResponse(
        content=content,
        model_name="deepseek-chat",
        usage=ModelUsage(input_tokens=500, output_tokens=300, total_tokens=800),
    )


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, model_api_key="test-key", **kwargs)


def run_analysis(service: ProfileAnalysisService, profile_data: dict):
    profile = ApplicantAnalysisInput.model_validate(profile_data)
    return asyncio.run(service.analyze(profile, "req_test123"))


def test_valid_output_is_returned_with_backend_metadata(
    profile_data: dict, valid_model_payload: dict
) -> None:
    client = FakeModelClient([model_response(valid_model_payload)])
    service = ProfileAnalysisService(settings(), client)
    result = run_analysis(service, profile_data)
    assert result.analysis_scope == "profile_only"
    assert result.meta.request_id == "req_test123"
    assert result.meta.prompt_version == "profile_analysis_v1@1.2.0"
    assert "未使用已核验院校项目数据" in " ".join(result.limitations)
    assert client.calls == 1


def test_markdown_fenced_json_is_parsed_without_leaking_wrapper(
    profile_data: dict, valid_model_payload: dict
) -> None:
    client = FakeModelClient([model_response(valid_model_payload, fenced=True)])
    result = run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert result.schema_version == "applicant_analysis_output.v1"


def test_invalid_structure_retries_once_then_succeeds(
    profile_data: dict, valid_model_payload: dict
) -> None:
    client = FakeModelClient(
        [
            ModelResponse("not json", "deepseek-chat", ModelUsage()),
            model_response(valid_model_payload),
        ]
    )
    result = run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert result.analysis_scope == "profile_only"
    assert client.calls == 2


def test_invalid_structure_twice_returns_stable_error(profile_data: dict) -> None:
    client = FakeModelClient(
        [
            ModelResponse("bad", "deepseek-chat", ModelUsage()),
            ModelResponse("still bad", "deepseek-chat", ModelUsage()),
        ]
    )
    with pytest.raises(AppError) as exc:
        run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert exc.value.code == "MODEL_OUTPUT_INVALID"
    assert client.calls == 2


def test_nonexistent_evidence_ref_is_rejected(
    profile_data: dict, valid_model_payload: dict
) -> None:
    broken = deepcopy(valid_model_payload)
    broken["direction_evidence"][0]["input_evidence_refs"] = ["core_courses[99]"]
    client = FakeModelClient([model_response(broken), model_response(broken)])
    with pytest.raises(AppError) as exc:
        run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "forbidden_text",
    [
        "你有 70% 的录取概率。",
        "这是你的保底选择。",
        "你已满足某项目申请门槛。",
        "某项目学费和截止日期适合你。",
        "香港示例大学适合你。",
        "相关实习能够增强你的申请竞争力。",
        "科研经历对申请研究型项目重要。",
        "英国院校通常要求提供这些经历。",
    ],
)
def test_forbidden_claims_are_rejected(
    profile_data: dict, valid_model_payload: dict, forbidden_text: str
) -> None:
    broken = deepcopy(valid_model_payload)
    broken["next_questions"][0] = forbidden_text
    client = FakeModelClient([model_response(broken), model_response(broken)])
    with pytest.raises(AppError) as exc:
        run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "out_of_scope_question",
    [
        "你是否考虑其他目标地区？",
        "你还想申请哪些具体学校？",
        "请说明你计划申请哪些项目。",
    ],
)
def test_out_of_scope_next_questions_are_rejected(
    profile_data: dict, valid_model_payload: dict, out_of_scope_question: str
) -> None:
    broken = deepcopy(valid_model_payload)
    broken["next_questions"][0] = out_of_scope_question
    client = FakeModelClient([model_response(broken), model_response(broken)])
    with pytest.raises(AppError) as exc:
        run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


def test_transient_model_error_retries_once(
    profile_data: dict, valid_model_payload: dict
) -> None:
    client = FakeModelClient(
        [ModelClientError("timeout", True), model_response(valid_model_payload)]
    )
    result = run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert result.meta.model_name == "deepseek-chat"
    assert client.calls == 2


@pytest.mark.parametrize(
    ("kind", "expected_code", "expected_calls"),
    [
        ("not_configured", "MODEL_NOT_CONFIGURED", 1),
        ("authentication", "MODEL_AUTH_FAILED", 1),
        ("timeout", "MODEL_TIMEOUT", 2),
        ("rate_limit", "MODEL_UNAVAILABLE", 2),
    ],
)
def test_model_errors_map_to_public_contract(
    profile_data: dict, kind: str, expected_code: str, expected_calls: int
) -> None:
    error = ModelClientError(kind, kind in {"timeout", "rate_limit"})
    client = FakeModelClient([error] * expected_calls)
    with pytest.raises(AppError) as exc:
        run_analysis(ProfileAnalysisService(settings(), client), profile_data)
    assert exc.value.code == expected_code
    assert client.calls == expected_calls
