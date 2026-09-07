from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.config import Settings
from backend.app.db.migrations import (
    assert_database_at_head,
    current_database_revision,
)
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.services.alpha_quality_scanner import (
    AlphaQualityInputError,
    AlphaQualityScanner,
    load_alpha_quality_context,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Alpha dataset quality scan with hard fail-closed gates."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--generated-commit", required=True)
    parser.add_argument("--database-url")
    args = parser.parse_args(argv)
    database_url = args.database_url or Settings().database_url
    engine = create_database_engine(database_url)
    try:
        assert_database_at_head(engine)
        revision = current_database_revision(engine)
        if revision is None:
            raise AlphaQualityInputError("database has no Alembic revision")
        context = load_alpha_quality_context(
            root=args.root,
            generated_commit=args.generated_commit,
            alembic_revision=revision,
        )
        sessions = create_session_factory(engine)
        with sessions.begin() as session:
            report = AlphaQualityScanner(
                session,
                clock=lambda: datetime.now(timezone.utc),
            ).scan(context)
    except Exception:
        print(
            json.dumps(
                {"ready": False, "error": "ALPHA_QUALITY_SCAN_FAILED"},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    finally:
        engine.dispose()
    print(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
