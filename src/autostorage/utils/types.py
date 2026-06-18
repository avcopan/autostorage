"""Autostorage types."""

from pathlib import Path

import numpy as np
from sqlalchemy.types import JSON, String, TypeDecorator

TrajectoryIndices = list[int | list[int]]


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
