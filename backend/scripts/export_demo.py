"""Rebuild the public demo from synthetic input and the real rule engine.

No .env, API credentials, existing database, or external model is used.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.core.config import Settings
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.schemas.selection_advice import SelectionAdviceRequest
from backend.app.services.model_client import ModelClientError
from backend.app.services.program_catalog import ProgramCatalogService
from backend.app.services.selection_advice import SelectionAdviceService
from backend.scripts.bootstrap_internal_alpha import bootstrap_internal_alpha

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_TIME = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)


class OfflineModel:
    async def complete(self, messages):
        raise ModelClientError(kind="not_configured", retryable=False)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    profile = json.loads((ROOT / "backend/tests/fixtures/synthetic_profiles.json").read_text())["cross_discipline_missing_language"]
    profile["target_directions"] = ["computer_science", "artificial_intelligence", "aerospace_engineering", "low_altitude_economy"]
    payload = SelectionAdviceRequest.model_validate({
        "schema_version": "selection_advice_request.v1", "profile": profile,
        "rule_facts": {"institution_recognition": "unknown", "work_experience_months": None,
                       "materials": {"portfolio": None, "interview": None, "recommendation_letters": None}},
    })
    with TemporaryDirectory(prefix="skyoffer-demo-") as directory:
        settings = Settings(_env_file=None, model_api_key=None, app_env="test",
                            database_url=f"sqlite:///{directory}/demo.db")
        bootstrap_internal_alpha(settings)
        engine = create_database_engine(settings.database_url)
        try:
            with create_session_factory(engine)() as session:
                service = SelectionAdviceService(settings, model_client=OfflineModel(), clock=lambda: SNAPSHOT_TIME)
                result = asyncio.run(service.advise(payload, session=session, request_id="demo.synthetic.v1"))
        finally:
            engine.dispose()
    data = result.model_dump(mode="json")
    data["meta"]["duration_ms"] = 0
    write_json(ROOT / "frontend/demo/advice.json", data)
    write_json(ROOT / "frontend/demo/profile.json", profile)
    catalog = ProgramCatalogService(clock=lambda: SNAPSHOT_TIME)
    listing = catalog.list_programs().model_dump(mode="json")
    write_json(ROOT / "frontend/public/demo/catalog.json", listing)
    refs = [item["program_ref"] for item in listing["programs"]]
    write_json(ROOT / "frontend/demo/program-refs.json", refs)
    for ref in refs:
        write_json(ROOT / f"frontend/public/demo/programs/{ref}.json", catalog.get_program(ref).model_dump(mode="json"))
    print(f"Exported {len(refs)} programs and a synthetic rule-only result; no external model called.")


if __name__ == "__main__":
    main()
