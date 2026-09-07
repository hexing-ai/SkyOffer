from __future__ import annotations

from backend.app.core.config import get_settings
from backend.app.db.migrations import (
    assert_database_at_head,
    expected_head_revision,
    upgrade_database,
)
from backend.app.db.session import create_database_engine


def main() -> None:
    settings = get_settings()
    upgrade_database(settings.database_url)
    engine = create_database_engine(settings.database_url)
    try:
        assert_database_at_head(engine)
    finally:
        engine.dispose()
    print(f"SkyOffer database ready at revision {expected_head_revision()}.")


if __name__ == "__main__":
    main()
