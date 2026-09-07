from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.db.migrations import upgrade_database
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.app.schemas.selection_advice import SelectionAdviceRequest
from backend.app.services.alpha_candidate_importer import AlphaCandidateImporter
from backend.app.services.internal_alpha_quality import (
    load_internal_alpha_quality_context,
)
from backend.app.services.model_client import ModelResponse, ModelUsage
from backend.app.services.historical_reference import DEFAULT_HISTORICAL_REFERENCE_PATH
from backend.app.services.selection_advice import SelectionAdviceService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALPHA_ROOT = PROJECT_ROOT / "backend" / "data" / "alpha_v1"
FIXED_NOW = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)


class PackIds:
    def __init__(self, version_id: str, namespace: str) -> None:
        self.version_id = version_id
        self.namespace = namespace
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        if kind == "version":
            return self.version_id
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}.selection.test.{self.namespace}.{count}"


class ExplanationModel:
    def __init__(self):
        self.batch_sizes: list[int] = []

    async def complete(self, messages):
        content = messages[-1]["content"]
        raw = content.split("<rule_results>\n", 1)[1].split(
            "\n</rule_results>", 1
        )[0]
        programs = json.loads(raw)
        self.batch_sizes.append(len(programs))
        return ModelResponse(
            content=json.dumps(
                {
                    "schema_version": "selection_explanations.v1",
                    "items": [
                        {
                            "program_ref": item["program_ref"],
                            "summary": "当前已确认门槛与资料存在可追溯判断，仍需处理列出的不确定项。",
                            "strengths": ["已满足项由规则引擎直接确认。"],
                            "risks": ["人工审核项仍需补充材料或官方核验。"],
                            "next_actions": ["先补齐缺失信息，再复查所有高风险字段。"],
                        }
                        for item in programs
                    ],
                },
                ensure_ascii=False,
            ),
            model_name="fake-deepseek",
            usage=ModelUsage(),
        )


class InvalidPolicyModel:
    async def complete(self, messages):
        content = messages[-1]["content"]
        raw = content.split("<rule_results>\n", 1)[1].split(
            "\n</rule_results>", 1
        )[0]
        programs = json.loads(raw)
        return ModelResponse(
            content=json.dumps(
                {
                    "schema_version": "selection_explanations.v1",
                    "items": [
                        {
                            "program_ref": item["program_ref"],
                            "summary": "这是保底项目。",
                            "strengths": [],
                            "risks": [],
                            "next_actions": ["直接申请。"],
                        }
                        for item in programs
                    ],
                },
                ensure_ascii=False,
            ),
            model_name="unsafe-model",
            usage=ModelUsage(),
        )


@pytest.fixture
def selection_runtime(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'selection.sqlite3'}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    context = load_internal_alpha_quality_context(
        root=ALPHA_ROOT, generated_commit="selection-test"
    )
    for index, entry in enumerate(context.manifest.programs, start=1):
        with sessions.begin() as session:
            AlphaCandidateImporter(
                session,
                clock=lambda: FIXED_NOW,
                id_factory=PackIds(entry.candidate_version_id, str(index)),
            ).import_pack(
                pack=context.packs_by_ref[entry.pack_ref],
                scope=context.scope,
                idempotency_key=f"selection-test-{entry.pack_ref}",
            )
    yield database_url, engine, sessions
    engine.dispose()


def _request(profile_data: dict) -> SelectionAdviceRequest:
    profile_data["target_regions"] = ["hong_kong", "united_kingdom"]
    profile_data["target_directions"] = [
        "computer_science",
        "artificial_intelligence",
        "aerospace_engineering",
        "low_altitude_economy",
    ]
    return SelectionAdviceRequest.model_validate(
        {
            "schema_version": "selection_advice_request.v1",
            "profile": profile_data,
            "rule_facts": {
                "institution_recognition": "mainland_recognized",
                "work_experience_months": 6,
                "materials": {
                    "portfolio": True,
                    "interview": None,
                    "recommendation_letters": True,
                },
            },
        }
    )


def test_real_input_to_rules_ai_tiers_and_official_citations(
    selection_runtime, profile_data
):
    _url, _engine, sessions = selection_runtime
    model = ExplanationModel()
    service = SelectionAdviceService(
        Settings(model_api_key="test"),
        model_client=model,
        alpha_root=ALPHA_ROOT,
        clock=lambda: FIXED_NOW,
    )
    with sessions.begin() as session:
        response = asyncio.run(
            service.advise(
                _request(profile_data), session=session, request_id="req_selection_test"
            )
        )

    assert len(response.results) == 20
    assert model.batch_sizes == [5, 5, 5, 5]
    assert response.meta.model_name == "fake-deepseek"
    assert {item.recommendation_label for item in response.results}.issubset(
        {"冲刺", "主申", "相对稳妥", "待核验"}
    )
    assert all(item.field_judgments for item in response.results)
    assert all(
        citation.url.startswith("https://")
        for item in response.results
        for field in item.field_judgments
        for citation in field.citations
    )
    assert all(
        citation.field_key == field.field_key
        for item in response.results
        for field in item.field_judgments
        for citation in field.citations
    )
    assert "录取概率" in response.disclaimer
    assert "保底" in response.disclaimer
    additions = {
        item.program_ref
        for item in response.results
        if item.program_ref.startswith("program.uk.imperial.")
    }
    assert additions
    assert all(
        item.recommendation_label == "待核验"
        for item in response.results
        if item.program_ref in additions
    )
    hku_ai = next(
        item
        for item in response.results
        if item.program_ref == "program.hk.hku.msc_artificial_intelligence"
    )
    hku_fields = {item.field_key: item for item in hku_ai.field_judgments}
    assert hku_ai.historical_reference is None
    assert hku_ai.recommendation_label == "冲刺"
    assert hku_fields["requirements.degree"].coverage_status == "confirmed"
    assert hku_fields["requirements.degree"].status == "met"
    assert hku_fields["requirements.language"].coverage_status == "confirmed"
    assert hku_fields["requirements.prerequisite_courses"].coverage_status == "confirmed"
    assert hku_fields["requirements.prerequisite_courses"].status == "unmet"
    assert {
        citation.evidence_id
        for key in (
            "requirements.degree",
            "requirements.language",
            "requirements.prerequisite_courses",
        )
        for citation in hku_fields[key].citations
    } == {
        "evidence.hku.mscai.admissions.2027.v1",
        "evidence.hku.tpg.requirements.2027.v1",
    }
    assert all(
        item.historical_reference is not None
        or any(field.coverage_status == "confirmed" for field in item.field_judgments)
        for item in response.results
    )


def test_selection_advice_api_runs_complete_flow(selection_runtime, profile_data):
    database_url, engine, sessions = selection_runtime
    service = SelectionAdviceService(
        Settings(model_api_key="test", database_url=database_url),
        model_client=ExplanationModel(),
        alpha_root=ALPHA_ROOT,
        clock=lambda: FIXED_NOW,
    )
    app = create_app(
        settings=Settings(model_api_key="test", database_url=database_url),
        phase3_session_factory=sessions,
        selection_advice_service=service,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/selection-advice",
            json=_request(profile_data).model_dump(mode="json"),
        )

    assert response.status_code == 200
    assert response.json()["schema_version"] == "selection_advice_response.v1"
    assert len(response.json()["results"]) == 20


def test_historical_reference_is_separate_from_2027_tier(
    selection_runtime, profile_data, tmp_path
):
    _database_url, _engine, sessions = selection_runtime
    request = _request(profile_data)
    original_service = SelectionAdviceService(
        Settings(model_api_key="test"),
        model_client=ExplanationModel(),
        alpha_root=ALPHA_ROOT,
        clock=lambda: FIXED_NOW,
    )
    with sessions.begin() as session:
        original = asyncio.run(
            original_service.advise(
                request, session=session, request_id="req_history_original"
            )
        )

    altered = json.loads(DEFAULT_HISTORICAL_REFERENCE_PATH.read_text(encoding="utf-8"))
    hku_cs = next(
        item
        for item in altered["programs"]
        if item["program_ref"] == "program.hk.hku.msc_computer_science"
    )
    degree = next(
        item for item in hku_cs["fields"] if item["field_key"] == "requirements.degree"
    )
    degree["requirement"]["rule"]["allowed_values"] = ["master"]
    altered_path = tmp_path / "historical-altered.json"
    altered_path.write_text(json.dumps(altered, ensure_ascii=False), encoding="utf-8")

    altered_service = SelectionAdviceService(
        Settings(model_api_key="test"),
        model_client=ExplanationModel(),
        alpha_root=ALPHA_ROOT,
        historical_reference_path=altered_path,
        clock=lambda: FIXED_NOW,
    )
    with sessions.begin() as session:
        changed = asyncio.run(
            altered_service.advise(
                request, session=session, request_id="req_history_changed"
            )
        )

    original_by_ref = {item.program_ref: item for item in original.results}
    changed_by_ref = {item.program_ref: item for item in changed.results}
    assert len([item for item in original.results if item.historical_reference]) == 14
    historical_citations = [
        citation
        for item in original.results
        if item.historical_reference
        for field in item.historical_reference.field_judgments
        for citation in field.citations
    ]
    assert historical_citations
    assert all(citation.academic_year == "2026-27" for citation in historical_citations)
    assert all(citation.url.startswith("https://") for citation in historical_citations)
    assert all(citation.source_version for citation in historical_citations)
    assert all(citation.verified_at for citation in historical_citations)
    assert all(len(citation.snapshot_sha256) == 64 for citation in historical_citations)
    assert {
        key: item.recommendation_tier for key, item in original_by_ref.items()
    } == {
        key: item.recommendation_tier for key, item in changed_by_ref.items()
    }
    assert (
        original_by_ref["program.hk.hku.msc_computer_science"]
        .historical_reference.reference_label
        == "部分满足"
    )
    assert (
        changed_by_ref["program.hk.hku.msc_computer_science"]
        .historical_reference.reference_label
        == "未满足"
    )


def test_model_cannot_turn_results_into_guarantees(selection_runtime, profile_data):
    database_url, _engine, sessions = selection_runtime
    service = SelectionAdviceService(
        Settings(model_api_key="test", database_url=database_url, model_max_retries=0),
        model_client=InvalidPolicyModel(),
        alpha_root=ALPHA_ROOT,
        clock=lambda: FIXED_NOW,
    )
    app = create_app(
        settings=Settings(model_api_key="test", database_url=database_url),
        phase3_session_factory=sessions,
        selection_advice_service=service,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/selection-advice",
            json=_request(profile_data).model_dump(mode="json"),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["model_name"] == "deterministic-fallback"
    assert "保底项目" not in response.text
    assert all("规则结果" in item["explanation"]["summary"] for item in body["results"])


def test_model_fallback_can_be_disabled(selection_runtime, profile_data):
    database_url, _engine, sessions = selection_runtime
    service = SelectionAdviceService(
        Settings(
            model_api_key="test",
            database_url=database_url,
            model_max_retries=0,
            model_fallback_enabled=False,
        ),
        model_client=InvalidPolicyModel(),
        alpha_root=ALPHA_ROOT,
        clock=lambda: FIXED_NOW,
    )
    app = create_app(
        settings=Settings(model_api_key="test", database_url=database_url),
        phase3_session_factory=sessions,
        selection_advice_service=service,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/selection-advice",
            json=_request(profile_data).model_dump(mode="json"),
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_OUTPUT_INVALID"


def test_selection_advice_page_exposes_real_mvp_form():
    app = create_app(settings=Settings(model_api_key="test"))
    with TestClient(app) as client:
        response = client.get("/advice")
        script = client.get("/static/advice.js")
        stylesheet = client.get("/static/advice.css")

    assert response.status_code == 200
    assert "生成可核验选校建议" in response.text
    assert "不是录取预测" in response.text
    assert 'id="advice-form"' in response.text
    assert "/api/v1/selection-advice" in script.text
    assert "innerHTML" not in script.text
    assert "prefers-reduced-motion" in stylesheet.text
    assert "[hidden]" in stylesheet.text
