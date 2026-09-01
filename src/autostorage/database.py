"""SQLite database connection management."""

import json
from functools import partial
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

# Ensure all modules are loaded with the database
from . import events  # noqa: F401
from .models import *  # noqa: F403

__all__ = ["Database"]


class Database:
    """
    Database connection manager.

    Attributes
    ----------
    path
        Path to SQLite database file.
    engine
        SQLAlchemy engine instance.
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

    def session(self) -> Session:
        """Return a fresh `Session` bound to this database's engine.

        Note
        ----
        A new `Session` is created per call; use it as a context manager
        (`with database.session() as session: ...`) to close it on exit.
        Nothing is committed automatically — call `session.commit()` explicitly.
        """
        return Session(self.engine)

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()
