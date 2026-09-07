from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from backend.app.db.session import create_database_engine, create_session_factory


def phase3_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.phase3_session_factory
    if factory is None:
        settings = request.app.state.settings
        engine = create_database_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        factory = create_session_factory(engine)
        request.app.state.phase3_db_engine = engine
        request.app.state.phase3_session_factory = factory
    with factory.begin() as session:
        yield session
