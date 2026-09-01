"""Autostorage types."""

import zlib
from enum import StrEnum
from io import BytesIO
from typing import Any

import numpy as np
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field

__all__ = ["CompressedArrayTypeDecorator", "Role"]


def _fk_field(target: str, *, nullable: bool = False, index: bool = True) -> Any:  # noqa: ANN401
    """Build a standard foreign-key Field with ON DELETE CASCADE."""
    return Field(
        default=None,
        foreign_key=target,
        ondelete="CASCADE",
        nullable=nullable,
        index=index,
    )


class CompressedArrayTypeDecorator(TypeDecorator):
    """Stores a NumPy array as zlib-compressed binary data in the DB.

    Shape and dtype are preserved via the NumPy `.npy` format, so this works for
    arrays of any dimensionality (flat vectors, coordinate matrices, Hessians, ...).
    """

    impl = LargeBinary
    cache_ok = True

    def __init__(self, dtype: Any = np.float64, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        self.dtype = dtype

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:  # noqa: ANN401, ARG002
        """Convert a NumPy array to zlib-compressed `.npy` bytes for the database."""
        if value is None:
            return None
        buffer = BytesIO()
        np.save(buffer, np.asarray(value, dtype=self.dtype), allow_pickle=False)
        return zlib.compress(buffer.getvalue())

    def process_result_value(
        self,
        value: bytes | None,
        dialect: Any,  # noqa: ANN401, ARG002
    ) -> np.ndarray | None:
        """Convert compressed `.npy` bytes from the database back to a NumPy array."""
        if value is None:
            return None
        return np.load(BytesIO(zlib.decompress(value)), allow_pickle=False)


class Role(StrEnum):
    """Relationship between calculations and geometries/trajectories."""

    INPUT = "input"
    OUTPUT = "output"
