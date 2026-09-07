from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.config import Settings
from backend.app.db.migrations import assert_database_at_head
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.services.internal_alpha_quality import (
    InternalAlphaQualityScanner,
    load_internal_alpha_quality_context,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit the Candidate-only internal Alpha dataset."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--generated-commit", required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--generated-at")
    args = parser.parse_args(argv)

    generated_at = (
        datetime.fromisoformat(args.generated_at.replace("Z", "+00:00"))
        if args.generated_at
        else datetime.now(timezone.utc)
    )
    engine = create_database_engine(args.database_url or Settings().database_url)
    try:
        assert_database_at_head(engine)
        context = load_internal_alpha_quality_context(
            root=args.root,
            generated_commit=args.generated_commit,
        )
        sessions = create_session_factory(engine)
        with sessions.begin() as session:
            report = InternalAlphaQualityScanner(
                session, clock=lambda: generated_at
            ).scan(context)
    except Exception:
        print(
            json.dumps(
                {"ready_for_internal_mvp": False, "error": "INTERNAL_ALPHA_SCAN_FAILED"},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    finally:
        engine.dispose()
    print(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    )
    return 0 if report.ready_for_internal_mvp else 1


if __name__ == "__main__":
    raise SystemExit(main())
