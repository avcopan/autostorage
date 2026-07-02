"""Database connection."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.sql.expression import Select, SelectOfScalar

# Ensure all modules are loaded with the database
from .events import *  # noqa: F403
from .models import *  # noqa: F403

T = TypeVar("T")

SelectStatement = Select[T] | SelectOfScalar[T]

__all__ = ["Database", "Select", "SelectOfScalar", "SelectStatement"]


class Database:
    """
    Database connection manager.

    Attributes
    ----------
    path
        Path to SQLite database file.
    engine
        SQLAlchemy engine instance.
    _session
        Persistent database session.
    """

    def __init__(
        self, path: str | Path, *, echo: bool = False, wal: bool = False
    ) -> None:
        """
        Initialize database connection manager.

        Parameters
        ----------
        path
            Path to the SQLite database file.
        echo, optional
            If True, SQL statements will be logged to the standard output.
            If False, no logging is performed.
        wal, optional
            If True, attempt to enable WAL journal mode for better concurrent
            read/write performance.
        """
        self.path = Path(path)
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            echo=echo,
            # Allow multithreading
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            """Set WAL pragma."""
            cursor = dbapi_connection.cursor()
            if wal:
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                except OperationalError:
                    cursor.execute("PRAGMA foreign_mode=DELETE")
            # SQLite ignores FK constraints unless enabled
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        SQLModel.metadata.create_all(self.engine)
        self._session: Session = Session(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a new database session."""
        try:
            yield self._session
        except IntegrityError:
            self._session.rollback()
            raise

    def add[RowT: SQLModel](self, row: RowT) -> None:
        """Add row to session."""
        with self.session() as session:
            session.add(row)

    def merge[RowT: SQLModel](self, row: RowT) -> RowT:
        """Merge row into current session and commit, returning the merged row."""
        with self.session() as session:
            return session.merge(row)

    def flush(self) -> None:
        """Flush pending changes to the database without committing."""
        with self.session() as session:
            session.flush()

    def commit(self) -> None:
        """Commit database session."""
        with self.session() as session:
            session.commit()

    def delete[RowT: SQLModel](self, row: RowT) -> None:
        """Delete row from database."""
        with self.session() as session:
            session.delete(row)
            session.commit()

    def get[RowT: SQLModel](self, model: type[RowT], row_id: int) -> RowT:
        """Get row from database."""
        with self.session() as session:
            row = session.get(model, row_id)
            if row is not None:
                return row

        msg = f"{model} with {row_id = } not found."
        raise LookupError(msg)

    def exec_first[RowT: SQLModel](self, stmt: SelectStatement[RowT]) -> RowT | None:
        """Return the first match to a statement."""
        with self.session() as session:
            return session.exec(stmt).first()

    def exec_one[RowT](self, stmt: SelectStatement[RowT]) -> RowT:
        """Return the first match to a statement."""
        with self.session() as session:
            return session.exec(stmt).one()

    def exec_all[RowT](self, stmt: SelectStatement[RowT]) -> Iterator[RowT]:
        """Yield all matches to a statement."""
        with self.session() as session:
            yield from session.exec(stmt).all()

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()
