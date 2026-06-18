"""Database connection."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.sql.expression import SelectOfScalar

from .models import *  # noqa: F403
from .models.base import BaseRowT


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
        self.engine = create_engine(f"sqlite:///{self.path}", echo=echo)
        SQLModel.metadata.create_all(self.engine)

        self._session: Session = Session(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a persisted session."""
        yield self._session

    def add(self, row: BaseRowT) -> BaseRowT:
        """Update existing row or insert if not found."""
        with self.session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)

            return row

    def delete(self, row: BaseRowT) -> None:
        """Delete row from database."""
        with self.session() as session:
            session.delete(row)
            session.commit()

    def get(self, model: type[BaseRowT], row_id: int) -> BaseRowT:
        """Get row from database."""
        with self.session() as session:
            row = session.get(model, row_id)
            if row is not None:
                return row

        msg = f"{model} with {row_id = } not found."
        raise LookupError(msg)

    def exec_first(self, stmt: SelectOfScalar[BaseRowT]) -> BaseRowT | None:
        """Return the first match to a statement."""
        with self.session() as sess:
            return sess.exec(stmt).first()

    def exec_one(self, stmt: SelectOfScalar[BaseRowT]) -> BaseRowT:
        """Return the first match to a statement."""
        with self.session() as sess:
            return sess.exec(stmt).one()

    def exec_all(self, stmt: SelectOfScalar[BaseRowT]) -> Iterator[BaseRowT]:
        """Yield all matches to a statement."""
        with self.session() as sess:
            yield from sess.exec(stmt).all()

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()
