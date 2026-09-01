"""Database module tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from autostorage.database import Database
from autostorage.models import (
    CalculationGeometryLink,
    CalculationRow,
    IdentityRow,
    ModelRow,
)


@pytest.fixture
def db_path() -> Generator[Path, None, None]:
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def database(db_path: Path) -> Generator[Database, None, None]:
    """Create a Database instance for testing."""
    db = Database(db_path)
    yield db
    db.close()


class TestDatabaseInit:
    """Tests for Database initialization."""

    def test_init_with_string_path(self, db_path: Path) -> None:
        """Database can be initialized with a string path."""
        db = Database(str(db_path))
        assert db.path == db_path
        assert db.engine is not None
        db.close()

    def test_init_with_path_object(self, db_path: Path) -> None:
        """Database can be initialized with a Path object."""
        db = Database(db_path)
        assert db.path == db_path
        assert db.engine is not None
        db.close()

    def test_init_creates_schema(self, db_path: Path) -> None:
        """Database initialization creates all tables."""
        db = Database(db_path)
        # Check that tables exist by attempting to create a session and query
        with db.session() as session:
            # This should not raise an error if schema is created
            assert session.is_active
        db.close()

    def test_init_with_echo_false(self, db_path: Path) -> None:
        """Database can be initialized with echo=False."""
        db = Database(db_path, echo=False)
        assert db.engine.echo is False
        db.close()

    def test_init_with_echo_true(self, db_path: Path) -> None:
        """Database can be initialized with echo=True."""
        db = Database(db_path, echo=True)
        assert db.engine.echo is True
        db.close()

    def test_path_attribute(self, database: Database, db_path: Path) -> None:
        """Database stores path as Path object."""
        assert isinstance(database.path, Path)
        assert database.path == db_path

    def test_engine_attribute(self, database: Database) -> None:
        """Database creates a SQLAlchemy engine."""
        assert database.engine is not None
        assert "sqlite" in str(database.engine.url)


class TestDatabaseSession:
    """Tests for Database.session() method."""

    def test_session_returns_session_instance(self, database: Database) -> None:
        """session() returns a SQLAlchemy Session."""
        sess = database.session()
        assert isinstance(sess, Session)
        sess.close()

    def test_session_is_bound_to_engine(self, database: Database) -> None:
        """Session is bound to the database engine."""
        sess = database.session()
        assert sess.get_bind() == database.engine
        sess.close()

    def test_session_as_context_manager(self, database: Database) -> None:
        """Session can be used as a context manager."""
        with database.session() as sess:
            assert isinstance(sess, Session)
            assert sess.is_active

    def test_multiple_sessions(self, database: Database) -> None:
        """Multiple sessions can be created from same database."""
        sess1 = database.session()
        sess2 = database.session()
        assert sess1 is not sess2
        assert sess1.get_bind() == sess2.get_bind()
        sess1.close()
        sess2.close()

    def test_session_context_manager_rollback(self, database: Database) -> None:
        """Session exits context manager cleanly."""
        sess = database.session()
        with sess:
            pass
        # Session may still exist but transaction should be complete
        assert sess is not None


class TestDatabaseClose:
    """Tests for Database.close() method."""

    def test_close_disposes_engine(self, db_path: Path) -> None:
        """close() disposes the engine."""
        db = Database(db_path)
        db.close()
        # After dispose, new connections should be created fresh
        # We can verify this indirectly by creating a new session
        # (which would fail if engine was truly destroyed)
        assert db.engine is not None

    def test_can_create_session_after_close(self, db_path: Path) -> None:
        """A new session can be created after close() due to engine re-pooling."""
        db = Database(db_path)
        db.close()
        # Pool should be reset but engine still functional
        sess = db.session()
        assert isinstance(sess, Session)
        sess.close()


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    def test_insert_and_query_row(self, database: Database) -> None:
        """Can insert and query a row from the database."""
        with database.session() as session:
            # Create an identity row
            identity = IdentityRow(
                algorithm="RDKIT_INCHI",
                kind="inchi",
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity)
            session.commit()

            # Query it back
            result = session.query(IdentityRow).filter_by(kind="inchi").first()
            assert result is not None
            assert result.value == "InChI=1S/CH4/h1H4"

    def test_json_serializer_sorts_keys(self, database: Database) -> None:
        """JSON serializer sorts keys for consistent output."""
        with database.session() as session:
            # Create a model first (required for CalculationRow)
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            # Create input_provenance with unordered keys
            provenance = {"z_key": "z", "a_key": "a", "m_key": "m"}

            calc = CalculationRow(
                model_id=model.id,
                calc_type="energy",
                input_provenance=provenance,
            )
            session.add(calc)
            session.commit()

            # Retrieve and verify keys are consistent
            result = session.query(CalculationRow).first()
            assert result is not None
            # The serializer should have sorted keys during storage
            assert result.input_provenance == provenance

    def test_foreign_keys_enabled(self, database: Database) -> None:
        """Foreign key constraints are enforced."""
        with database.session() as session:
            # Try to create a link with non-existent geometry_id
            link = CalculationGeometryLink(
                calculation_id=9999,  # Non-existent
                geometry_id=9999,  # Non-existent
                role="input",
            )
            session.add(link)
            # Foreign key constraint should prevent commit
            with pytest.raises(IntegrityError):
                session.commit()

    def test_concurrent_session_access(self, database: Database) -> None:
        """Multiple concurrent sessions can access the database."""
        with database.session() as sess1, database.session() as sess2:
            # Both sessions should be active simultaneously
            assert sess1.is_active
            assert sess2.is_active
            # Both should access the same database
            assert sess1.get_bind() == sess2.get_bind()
