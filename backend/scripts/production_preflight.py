from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text

from backend.app.core.config import Settings
from backend.app.db.migrations import assert_database_at_head, expected_head_revision
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.services.internal_alpha_quality import (
    InternalAlphaQualityScanner,
    load_internal_alpha_quality_context,
)
from backend.app.services.selection_advice import DEFAULT_ALPHA_ROOT


def production_preflight(settings: Settings) -> dict[str, object]:
    settings.assert_runtime_ready()
    engine = create_database_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    sessions = create_session_factory(engine)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        assert_database_at_head(engine)
        context = load_internal_alpha_quality_context(
            root=DEFAULT_ALPHA_ROOT,
            generated_commit=settings.app_version,
        )
        with sessions.begin() as session:
            report = InternalAlphaQualityScanner(
                session,
                clock=lambda: datetime.now(UTC),
            ).scan(context)
        if not report.ready_for_internal_mvp:
            raise RuntimeError("internal Alpha dataset is not ready")
        return {
            "valid": True,
            "version": settings.app_version,
            "database_revision": expected_head_revision(),
            "dataset_id": report.dataset_id,
            "program_count": report.program_count,
        }
    finally:
        engine.dispose()

def main() -> int:
    print(
        json.dumps(
            production_preflight(Settings()),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
