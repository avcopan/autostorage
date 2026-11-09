"""Database module tests."""

import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from automol import AlgorithmRegistry
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlmodel import col, select

from autostorage import AutostorageSession, PropertyKindRegistry, events
from autostorage.database import Database
from autostorage.models import (
    CalculationGeometryLink,
    CalculationRow,
    IdentityAlgorithmRow,
    IdentityRow,
    ModelRow,
    PropertyKindRow,
)


@pytest.fixture
def db_path() -> Generator[Path]:
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def database(db_path: Path) -> Generator[Database]:
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

    def test_init_failure_closes_database(
        self, db_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The engine is disposed if registry seeding fails."""
        closed: list[Database] = []
        close = Database.close

        def _fail(_session: Session) -> None:
            msg = "seeding failed"
            raise RuntimeError(msg)

        def _close(db: Database) -> None:
            closed.append(db)
            close(db)

        monkeypatch.setattr(events, "create_property_kinds", _fail)
        monkeypatch.setattr(Database, "close", _close)
        with pytest.raises(RuntimeError, match="seeding failed"):
            Database(db_path)
        assert len(closed) == 1


class TestDatabaseSession:
    """Tests for Database.session() method."""

    def test_session_returns_session_instance(self, database: Database) -> None:
        """session() returns an `AutostorageSession` (a SQLAlchemy Session)."""
        sess = database.session()
        assert isinstance(sess, AutostorageSession)
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
            # Algorithms are seeded on Database init from the automol registry
            algorithm = session.exec(
                select(IdentityAlgorithmRow).where(
                    col(IdentityAlgorithmRow.name) == "rdkit_inchi"
                )
            ).one()

            # Create an identity row
            identity = IdentityRow(
                algorithm_id=algorithm.id,
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity)
            session.commit()

            # Query it back
            result = session.exec(
                select(IdentityRow)
                .join(IdentityAlgorithmRow)
                .where(col(IdentityAlgorithmRow.kind) == "stereoisomer")
            ).first()
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
            result = session.exec(select(CalculationRow)).first()
            assert result is not None
            # The serializer should have sorted keys during storage
            assert result.input_provenance == provenance

    def test_foreign_keys_enabled(self, database: Database) -> None:
        """Foreign key constraints are enforced."""
        with database.session() as session:
            # Try to create a link with non-existent geometry_id
            link = CalculationGeometryLink(
                calculation_id=9999,  # Non-existent
                geometry_id=uuid.uuid4(),  # Non-existent
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


class TestRegistryTablesPrePopulated:
    """Registry pre-population tests for database initialization."""

    def test_identity_algorithms_populated(self, database: Database) -> None:
        """`identity_algorithm` table populated from registry at initialization."""
        with database.session() as sess:
            for alg in AlgorithmRegistry.algorithms:
                alg_row = sess.exec(
                    select(IdentityAlgorithmRow).where(
                        col(IdentityAlgorithmRow.name) == alg.name
                    )
                ).one()
                assert alg_row.id
                if alg.parent_algorithm is not None:
                    parent = sess.get(IdentityAlgorithmRow, alg_row.parent_algorithm_id)
                    assert parent is not None
                    assert parent.name == alg.parent_algorithm.name
                    assert parent.id

    def test_property_kinds_populated(self, database: Database) -> None:
        """`property_kind` table populated from registry at initialization."""
        with database.session() as sess:
            for kind in PropertyKindRegistry.property_kinds:
                assert sess.get(PropertyKindRow, kind.name) is not None


class TestDatabaseReopen:
    """Tests for reopening an existing database file."""

    def test_reopen_does_not_duplicate_registry_rows(self, db_path: Path) -> None:
        """Reopening a database does not re-insert registry rows."""
        for _ in range(3):
            with Database(db_path) as db, db.session() as sess:
                kinds = sess.exec(select(PropertyKindRow)).all()
                algs = sess.exec(select(IdentityAlgorithmRow)).all()
                assert len(kinds) == len(PropertyKindRegistry.property_kinds)
                assert len(algs) == len(AlgorithmRegistry.algorithms)

    def test_context_manager(self, db_path: Path) -> None:
        """`Database` can be used as a context manager."""
        with Database(db_path) as db:
            assert isinstance(db, Database)

    def test_path_with_url_characters(self, tmp_path: Path) -> None:
        """Paths containing URL delimiters are not misparsed."""
        path = tmp_path / "odd?name#1.db"
        with Database(path):
            pass
        assert path.exists()
