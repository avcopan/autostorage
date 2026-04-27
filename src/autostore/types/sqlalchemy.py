"""SQLAlchemy types."""

from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

import numpy as np
from sqlalchemy.types import JSON, String, TypeDecorator
from sqlmodel import SQLModel

# Model Type
SQLModelT = TypeVar("SQLModelT", bound=SQLModel)
AttrT = TypeVar("AttrT", float, str, dict, list)

# Row ID Type Aliases
RowID = int
RowIDs = Sequence[RowID]


class FloatArrayTypeDecorator(TypeDecorator):
    """SQLAlchemy NDArray -> JSON type decorator."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201, ARG002
        """Convert NumPy array to list for database."""
        if value is None:
            return None
        if isinstance(value, np.ndarray):
            return value.tolist()
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201, ARG002
        """Convert list from database back to NumPy array."""
        if value is None:
            return None
        return np.array(value, dtype=float)


class PathTypeDecorator(TypeDecorator):
    """SQLAlchemy Path -> String type decorator."""

    impl = String  # Store paths as strings in the database
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201, ARG002
        """Convert Path object to a string for the database."""
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201, ARG002
        """Convert string from the database back to a Path object."""
        if value is not None:
            return Path(value)
        return value
