"""Database connection."""

from pathlib import Path
from typing import TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, select

from .models import *  # noqa: F403

ModelT = TypeVar("ModelT", bound=SQLModel)


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

    def write(self, *, row: ModelT) -> int:
        """
        Write row to database.

        Parameters
        ----------
        row
            Instance of a database model class.

        Returns
        -------
        row_id
            id corresponding to entry in model table.

        Raises
        ------
        SQLAlchemyError
            Database row failed to write.
        """
        try:
            with self.session() as session:
                session.add(row)
                session.commit()
                session.refresh(row)
                return row.id  # ty:ignore[unresolved-attribute]

        except SQLAlchemyError as e:
            msg = f"Failed to write {row = } to database."
            raise RuntimeError(msg) from e

    def fetch(self, *, model: type[ModelT], row_id: int) -> ModelT:
        """
        Fetch rows based on row id.

        Parameters
        ----------
        model
            Database model class, e.g. CalculationRow or GeometryRow.
        row_id
            id corresponding to entry in model table.

        Returns
        -------
        model
            Instance of a database model class.

        Raises
        ------
        LookupError
            Row ID is not found in model table.
        TypeError
            Return type is not a database model.
        """
        with self.session() as session:
            row = session.get(model, row_id)

            if row is None:
                msg = f"Unable to find `{model.__tablename__}` row with ID {id}."
                raise LookupError(msg)

            if not isinstance(row, model):
                msg = f"{row = }, {model = }"
                raise TypeError(msg)

            return row

    def query(
        self, *, model: type[ModelT], **attributes: float | str | None
    ) -> list[int | None]:
        """
        Query for existing rows based on Class attributes.

        Parameters
        ----------
        model
            Database model class, e.g. CalculationRow or GeometryRow.
        **attributes
            Database model class attributes, e.g. id = 1 or energy = -0.568.

        Returns
        -------
        row_ids
            ids corresponding to entries in model table.
        """
        with self.session() as session:
            statement = select(model)

            # Append Select constructs to statement
            for key, value in attributes.items():
                if hasattr(model, key):
                    statement = statement.where(getattr(model, key) == value)

            return [getattr(row, "id", None) for row in session.exec(statement).all()]

    def close(self) -> None:
        """Close the database connection.

        Seems to be needed only for testing with in-memory databases.
        """
        self.engine.dispose()
