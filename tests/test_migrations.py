"""Smoke test for Alembic migrations."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.command import upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import autostorage.database  # noqa: F401  (registers models on SQLModel.metadata)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test__migrations_upgrade_to_head_matches_current_models(tmp_path: Path) -> None:
    """Test that running all migrations reproduces the schema `create_all()` builds."""
    db_path = tmp_path / "migrated.db"
    config = Config(REPO_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            diff = compare_metadata(context, SQLModel.metadata)
    finally:
        engine.dispose()

    assert diff == []
