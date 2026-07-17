"""Database connection."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import ColumnExpressionArgument, event
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, OperationalError
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.sql.expression import Select, SelectOfScalar

# Ensure all modules are loaded with the database
from .events import *  # noqa: F403
from .models import *  # noqa: F403

type SelectStatement[T] = Select[T] | SelectOfScalar[T]

__all__ = ["Database", "Query", "Select", "SelectOfScalar", "SelectStatement"]


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
        """Yield the persistent database session.

        Note
        ----
        This yields the single, long-lived `Session` created in `__init__`,
        not a fresh session per call — rows returned from queries stay
        attached, so lazy-loaded relationships keep working after the `with`
        block exits. As a result, a `Database` instance is not safe for
        concurrent use by multiple threads: `check_same_thread=False` only
        allows the underlying DBAPI connection to be used from a different
        thread than it was created on (e.g. a single background worker), it
        does not make the `Session` itself thread-safe.
        """
        try:
            yield self._session
        except Exception:
            self._session.rollback()
            raise

    def add[RowT: SQLModel](self, row: RowT) -> None:
        """Add row to session."""
        with self.session() as session:
            session.add(row)

    def merge[RowT: SQLModel](self, row: RowT) -> RowT:
        """Merge row into current session and commit, returning the merged row."""
        with self.session() as session:
            merged = session.merge(row)
            session.commit()
            return merged

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
        """Return the single match to a statement."""
        with self.session() as session:
            try:
                return session.exec(stmt).one()
            except NoResultFound as exc:
                msg = f"No row found matching {stmt}."
                raise LookupError(msg) from exc
            except MultipleResultsFound as exc:
                msg = f"Multiple rows found matching {stmt}."
                raise LookupError(msg) from exc

    def exec_all[RowT](self, stmt: SelectStatement[RowT]) -> Iterator[RowT]:
        """Yield all matches to a statement."""
        with self.session() as session:
            yield from session.exec(stmt)

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()

    def query[RowT: SQLModel](self, model: type[RowT]) -> "Query[RowT]":
        """Start a chainable query against a model.

        Examples
        --------
        >>> # db.query(EnergyRow).where(EnergyRow.value > 0.0).all()
        """
        return Query(self, select(model))


class Query[RowT: SQLModel]:
    """Chainable query builder returned by Database.query()."""

    def __init__(self, db: Database, stmt: SelectStatement[RowT]) -> None:
        self._db = db
        self._stmt = stmt

    def where(self, *criteria: ColumnExpressionArgument[bool] | bool) -> "Query[RowT]":
        """Return a new Query with additional WHERE criteria."""
        return Query(self._db, self._stmt.where(*criteria))

    def join(
        self, target: type[SQLModel], *criteria: ColumnExpressionArgument[bool]
    ) -> "Query[RowT]":
        """Return a new Query with an additional JOIN."""
        return Query(self._db, self._stmt.join(target, *criteria))

    def order_by(self, *criteria: ColumnExpressionArgument[Any]) -> "Query[RowT]":
        """Return a new Query with ORDER BY criteria."""
        return Query(self._db, self._stmt.order_by(*criteria))

    def group_by(self, *criteria: ColumnExpressionArgument[Any]) -> "Query[RowT]":
        """Return a new Query with GROUP BY criteria."""
        return Query(self._db, self._stmt.group_by(*criteria))

    def having(self, *criteria: ColumnExpressionArgument[bool]) -> "Query[RowT]":
        """Return a new Query with HAVING criteria."""
        return Query(self._db, self._stmt.having(*criteria))

    def distinct(self) -> "Query[RowT]":
        """Return a new Query with DISTINCT applied."""
        return Query(self._db, self._stmt.distinct())

    def limit(self, n: int) -> "Query[RowT]":
        """Return a new Query limited to n rows."""
        return Query(self._db, self._stmt.limit(n))

    def offset(self, n: int) -> "Query[RowT]":
        """Return a new Query offset by n rows."""
        return Query(self._db, self._stmt.offset(n))

    def first(self) -> RowT | None:
        """Return the first matching row, or None."""
        return self._db.exec_first(self._stmt)

    def one(self) -> RowT:
        """Return exactly one matching row."""
        return self._db.exec_one(self._stmt)

    def all(self) -> Iterator[RowT]:
        """Yield all matching rows."""
        return self._db.exec_all(self._stmt)
