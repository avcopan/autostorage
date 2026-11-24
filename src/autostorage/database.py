"""SQLite database connection management."""

import json
from functools import partial
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from sqlalchemy import URL, create_engine, event
from sqlmodel import SQLModel

# Importing `events` also imports `models`, registering every table on
# `SQLModel.metadata` and every ORM listener before the schema is created.
from . import events

__all__ = ["Database"]


def _enable_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:  # noqa: ANN401
    """Enable foreign-key enforcement, which SQLite disables by default."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Database connection manager.

    Attributes:
        path: Path to SQLite database file.
        engine: SQLAlchemy engine instance.
    """

    def __init__(self, path: str | Path, *, echo: bool = False) -> None:
        """Initialize database connection manager.

        Args:
            path: Path to the SQLite database file.
            echo: If True, SQL statements will be logged to the standard output.
                If False, no logging is performed.
        """
        self.path = Path(path)
        self.engine = create_engine(
            URL.create("sqlite", database=str(self.path)),
            echo=echo,
            # Canonicalize dict key order so JSON-column equality filters (e.g.
            # `CalculationRow.input_provenance == prov`) match regardless of the
            # key insertion order used to build the Python dict being compared.
            json_serializer=partial(json.dumps, sort_keys=True),
            # Let the connection pool hand connections to other threads. Sessions
            # are not thread-safe: use a separate `session()` per thread.
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _enable_foreign_keys)

        try:
            SQLModel.metadata.create_all(self.engine)
            with self.session() as seed_session:
                events.create_identity_algorithms(seed_session)
                events.create_model_hash_algorithms(seed_session)
                events.create_property_kinds(seed_session)
        except BaseException:
            self.close()
            raise

    def session(self) -> events.AutostorageSession:
        """Return a fresh session bound to this database's engine.

        Note:
            A new session is created per call; use it as a context manager
            (`with database.session() as session: ...`) to close it on exit.
            Nothing is committed automatically — call `session.commit()` explicitly.
            Validation and automatic identities are only applied by sessions of
            type `AutostorageSession`, such as the ones returned here.
        """
        return events.AutostorageSession(self.engine)

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()

    def __enter__(self) -> Self:
        """Return this database, to be closed on exiting the context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the database connection."""
        self.close()
