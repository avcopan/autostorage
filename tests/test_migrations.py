"""Smoke test for Alembic migrations."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.command import upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlmodel import SQLModel

import autostorage.database  # noqa: F401  (registers models on SQLModel.metadata)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Expression-based unique indexes SQLite can't reflect (see CLAUDE.md's
# migrations note); `compare_metadata` silently skips them too, so they need
# a direct `sqlite_master` check to guard against a future migration
# dropping one by accident.
_NULL_SAFE_EXPRESSION_INDEXES = ("unique_model_null_safe", "unq_step_stages_null_safe")


@pytest.mark.filterwarnings(
    "ignore:Skipped unsupported reflection of expression-based index"
    ":sqlalchemy.exc.SAWarning"
)
@pytest.mark.filterwarnings(
    "ignore:autogenerate skipping metadata-specified expression-based index:UserWarning"
)
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

            index_names = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'index'")
                )
            }
    finally:
        engine.dispose()

    assert diff == []
    for index_name in _NULL_SAFE_EXPRESSION_INDEXES:
        assert index_name in index_names
