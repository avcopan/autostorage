"""Database connection."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.orm import selectinload
from sqlmodel import Session, SQLModel, create_engine, select

from .models import *  # noqa: F403
from .types import SQLModelT
from .utils import row_to_dict


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
        self.engine = create_engine(f"sqlite:///{self.path}", echo=echo)
        SQLModel.metadata.create_all(self.engine)

    def session(self) -> Session:
        """Create a new database session."""
        return Session(self.engine)

    def add(
        self,
        row: SQLModelT,
        *,
        eager_load: bool = False,
    ) -> SQLModelT:
        """
        Add row to database.

        Parameters
        ----------
        row
            Instance of a database model class.
        eager_load
            If True, fully eager loads sqlmodel relationships with model return.

        Returns
        -------
        Updated row instance.

        Raises
        ------
        SQLAlchemyError
            Database row failed to write.
        """
        with self.session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)

            if eager_load:  # Add eager loading for all relationships
                model = type(row)
                statement = select(model)
                for rel_name in model.__sqlmodel_relationships__:
                    statement = statement.options(
                        selectinload(getattr(model, rel_name))
                    )
                matches = session.exec(statement).first()
                if not matches:
                    msg = f"{row = } did not add to database."
                    raise RuntimeError(msg)
                return matches

            return row

    def delete(self, row: SQLModelT) -> None:
        """
        Delete a row from the database.

        Parameters
        ----------
        row
            Instance of a database model class.
        """
        with self.session() as session:
            session.delete(row)
            session.commit()

    def find(
        self,
        row: SQLModelT,
        *,
        eager_load: bool = False,
        exclude_defaults: bool = True,
        exclude_id: bool = False,
    ) -> Iterator[SQLModelT]:
        """
        Find matching rows in database.

        If no matches, adds and yields row instance.

        Parameters
        ----------
        row
            Instance of a database model class.
        session
            (Optional) Instance of an active session.
        eager_load
            If True, fully eager loads sqlmodel relationships with model return.
        exclude_defaults
            If True, exclude default values from model dump.
        exclude_id
            If True, exclude id field from model dump (if applicable).

        Yields
        ------
            Instance of a database "model".
        """
        data = row_to_dict(
            row, exclude_defaults=exclude_defaults, exclude_id=exclude_id
        )
        with self.session() as session:
            model = type(row)
            statement = select(model)

            for k, v in data.items():
                statement = statement.where(getattr(model, k) == v)

            if eager_load:  # Add eager loading for all relationships
                for rel_name in model.__sqlmodel_relationships__:
                    statement = statement.options(
                        selectinload(getattr(model, rel_name))
                    )

        yield from session.exec(statement)

    def find_or_add(
        self,
        row: SQLModelT,
        *,
        eager_load: bool = False,
        exclude_defaults: bool = True,
        exclude_id: bool = False,
    ) -> Iterator[SQLModelT]:
        """
        Find matching rows in database.

        If no matches, adds and yields row instance.

        Parameters
        ----------
        row
            Instance of a database model class.
        eager_load
            If True, fully eager loads sqlmodel relationships with model return.
        exclude_defaults
            If True, exclude default values from model dump.
        exclude_id
            If True, exclude id field from model dump (if applicable).

        Yields
        ------
            Instance of a database "model".
        """
        # Flag to avoid loading the whole iterator into memory.
        found_any = False

        for matching_row in self.find(
            row,
            eager_load=eager_load,
            exclude_defaults=exclude_defaults,
            exclude_id=exclude_id,
        ):
            found_any = True
            yield matching_row

        if not found_any:
            yield self.add(row=row)

    def close(self) -> None:
        """Close the database connection.

        Seems to be needed only for testing with in-memory databases.
        """
        self.engine.dispose()
