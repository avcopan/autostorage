"""SQLite database connection and session management."""

import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import Self

import click
from sqlalchemy import event
from sqlalchemy import select as sa_select
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.sql.expression import Select, SelectOfScalar

# Ensure all modules are loaded with the database
from .events import *  # noqa: F403
from .merge import MergeReport
from .merge import merge_databases as _merge_databases
from .models import *  # noqa: F403

type SelectStatement[T] = Select[T] | SelectOfScalar[T]

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

    def __init__(self, path: str | Path, *, echo: bool = False) -> None:
        """
        Initialize database connection manager.

        Parameters
        ----------
        path
            Path to the SQLite database file.
        echo, optional
            If True, SQL statements will be logged to the standard output.
            If False, no logging is performed.
        """
        self.path = Path(path)
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            echo=echo,
            # Canonicalize dict key order so JSON-column equality filters (e.g.
            # `CalculationRow.input_provenance == prov`) match regardless of the
            # key insertion order used to build the Python dict being compared.
            json_serializer=partial(json.dumps, sort_keys=True),
            # Allow multithreading
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            """Set SQLite pragmas."""
            cursor = dbapi_connection.cursor()
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
        """Add row to session.

        Note
        ----
        The row is not validated or written to the database until the next `flush()` or
        `commit()`. Integrity/shape errors (unique constraints, the shape event
        listeners) raise there, which may be far removed from this call.
        """
        with self.session() as session:
            session.add(row)

    def add_all[RowT: SQLModel](self, rows: Iterable[RowT]) -> None:
        """Add multiple rows to session.

        Note
        ----
        Bulk `add()`. Same staging-only caveat applies.
        """
        with self.session() as session:
            session.add_all(rows)

    def merge[RowT: SQLModel](self, row: RowT) -> RowT:
        """Merge row into current session and commit, returning the merged row."""
        with self.session() as session:
            merged = session.merge(row)
            session.commit()
            return merged

    def merge_from(self, source_db: "Database", *, commit: bool = True) -> MergeReport:
        """Merge another database's contents into this one.

        Unlike `merge()` (a same-session upsert of a single row), this
        copies every row from a separate `source_db` into this database,
        remapping ids/foreign keys and deduplicating content-unique rows.

        See Also
        --------
        autostorage.merge
        """
        return _merge_databases(target=self, source=source_db, commit=commit)

    def flush(self) -> None:
        """Flush pending changes to the database without committing.

        Note
        ----
        Unlike `commit()`, this doesn't trigger SQLAlchemy's default `expire_on_commit`
        behavior, so an already-loaded object whose row was removed by a DB-level
        `ondelete="CASCADE"` during this flush would be read back stale. `expire_all()`
        forces those objects to reload (or raise) on next access instead.
        """
        with self.session() as session:
            session.flush()
            session.expire_all()

    def commit(self) -> None:
        """Commit database session."""
        with self.session() as session:
            session.commit()

    def delete[RowT: SQLModel](self, row: RowT) -> None:
        """Delete row from database."""
        with self.session() as session:
            session.delete(row)
            session.commit()

    def get_or_none[RowT: SQLModel](
        self, model: type[RowT], row_id: int
    ) -> RowT | None:
        """Get row from database, returning `None` instead of raising on a miss."""
        with self.session() as session:
            return session.get(model, row_id)

    def get[RowT: SQLModel](self, model: type[RowT], row_id: int) -> RowT:
        """Get row from database."""
        row = self.get_or_none(model, row_id)
        if row is not None:
            return row

        msg = f"{model} with {row_id = } not found."
        raise LookupError(msg)

    def exec_first[RowT: SQLModel](self, stmt: SelectStatement[RowT]) -> RowT | None:
        """Return the first match to a statement."""
        with self.session() as session:
            return session.exec(stmt).first()

    def exec_one[RowT: SQLModel](self, stmt: SelectStatement[RowT]) -> RowT:
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

    def exec_all[RowT: SQLModel](self, stmt: SelectStatement[RowT]) -> list[RowT]:
        """Return all matches to a statement."""
        with self.session() as session:
            return list(session.exec(stmt).all())

    def exists[RowT: SQLModel](self, stmt: SelectStatement[RowT]) -> bool:
        """Return whether any row matches a statement.

        Executes as a single `EXISTS` subquery instead of `exec_first`, so a matching
        row is never materialized.
        """
        with self.session() as session:
            return bool(
                session.exec(sa_select(stmt.exists())).scalar()  # ty:ignore[no-matching-overload]
            )

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()

    def __enter__(self) -> Self:
        """Enter a `with Database(...) as db:` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: object,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back on exception, then close the database connection."""
        del exc_value, traceback
        if exc_type is not None:
            self._session.rollback()
        self.close()


@click.command(name="autostorage-merge")
@click.argument("target", type=click.Path(path_type=Path))
@click.argument("source", type=click.Path(path_type=Path))
def merge_databases(target: Path, source: Path) -> None:
    """Merge one on-disk database's contents into another, as a CLI command.

    Installed as the ``autostorage-merge`` console script (see ``[project.scripts]`` in
    ``pyproject.toml``); also runnable via ``python -m autostorage.database``.
    """
    with Database(target) as target_db, Database(source) as source_db:
        report = _merge_databases(target=target_db, source=source_db)

    click.echo(f"Copied: {report.copied}")
    click.echo(f"Reused: {report.reused}")


if __name__ == "__main__":
    merge_databases()
