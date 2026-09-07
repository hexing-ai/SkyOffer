"""Phase 3 persistence primitives.

This package intentionally exposes database infrastructure only. Business state
transitions and publication services are added in later Phase 3 batches.
"""

from backend.app.db.base import Base
from backend.app.db.session import create_database_engine, create_session_factory

__all__ = ["Base", "create_database_engine", "create_session_factory"]
