from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from backend.app.db.session import create_database_engine


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPTS = PROJECT_ROOT / "backend" / "alembic"


class DatabaseRevisionError(RuntimeError):
    """Raised when a database is not at the expected migration revision."""


def build_alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPTS))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_database(database_url: str, revision: str = "head") -> None:
    engine = create_database_engine(database_url)
    engine.dispose()
    command.upgrade(build_alembic_config(database_url), revision)


def expected_head_revision() -> str:
    script = ScriptDirectory.from_config(build_alembic_config("sqlite://"))
    head = script.get_current_head()
    if head is None:
        raise DatabaseRevisionError("数据库迁移基线不存在。")
    return head


def current_database_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def assert_database_at_head(engine: Engine) -> None:
    if current_database_revision(engine) != expected_head_revision():
        raise DatabaseRevisionError("数据库版本不匹配，服务拒绝启动。")
