"""Autostorage types."""

import json
import zlib
from enum import StrEnum
from io import BytesIO
from typing import Any

import numpy as np
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

__all__ = [
    "AxisKind",
    "CompressedArrayTypeDecorator",
    "CompressedJSONTypeDecorator",
    "IdentityKind",
    "Role",
]

MAX_DECOMPRESSED_BYTES = 1 << 30
"""Upper bound on the decompressed size of a stored blob (guards against zip bombs)."""


def _decompress(data: bytes, max_size: int = MAX_DECOMPRESSED_BYTES) -> bytes:
    """Decompress zlib `data`, refusing to inflate beyond `max_size` bytes.

    Raises:
        ValueError: If the data would inflate beyond `max_size` bytes, or if the
            compressed stream is truncated.
    """
    decompressor = zlib.decompressobj()
    result = decompressor.decompress(data, max_size)
    if decompressor.unconsumed_tail:
        msg = f"Decompressed data exceeds the {max_size}-byte limit."
        raise ValueError(msg)
    if not decompressor.eof:
        msg = (
            "Compressed data is truncated, or decompresses beyond the "
            f"{max_size}-byte limit."
        )
        raise ValueError(msg)
    return result


class CompressedArrayTypeDecorator(TypeDecorator):
    """Stores a NumPy array as zlib-compressed binary data in the DB.

    Shape and dtype are preserved via the NumPy `.npy` format, so this works for
    arrays of any dimensionality (flat vectors, coordinate matrices, Hessians, ...).
    """

    impl = LargeBinary
    cache_ok = True

    def __init__(
        self,
        dtype: Any = np.float64,  # noqa: ANN401
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Create the decorator, storing arrays as `dtype` (or as given if None)."""
        super().__init__(*args, **kwargs)
        self.dtype = dtype

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:  # noqa: ANN401, ARG002
        """Convert a NumPy array to zlib-compressed `.npy` bytes for the database."""
        if value is None:
            return None
        buffer = BytesIO()
        array = np.asarray(value, dtype=self.dtype)
        np.save(buffer, array, allow_pickle=False)
        return zlib.compress(buffer.getvalue())

    def process_result_value(
        self,
        value: bytes | None,
        dialect: Any,  # noqa: ANN401, ARG002
    ) -> np.ndarray | None:
        """Convert compressed `.npy` bytes from the database back to a NumPy array."""
        if value is None:
            return None
        return np.load(BytesIO(_decompress(value)), allow_pickle=False)


class CompressedJSONTypeDecorator(TypeDecorator):
    """Stores a JSON-serializable value as zlib-compressed binary data in the DB."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:  # noqa: ANN401, ARG002
        """Convert a value to zlib-compressed JSON bytes for the database."""
        if value is None:
            return None
        return zlib.compress(json.dumps(value, separators=(",", ":")).encode())

    def process_result_value(self, value: bytes | None, dialect: Any) -> Any:  # noqa: ANN401, ARG002
        """Convert compressed JSON bytes from the database back to a value."""
        if value is None:
            return None
        return json.loads(_decompress(value))


class Role(StrEnum):
    """Relationship between calculations and geometries/trajectories."""

    INPUT = "input"
    OUTPUT = "output"


class IdentityKind(StrEnum):
    """Category of molecular identity, from coarsest to finest."""

    FORMULA = "formula"
    ISOMER = "isomer"
    STEREOISOMER = "stereoisomer"
    CONFORMER = "conformer"


class AxisKind(StrEnum):
    """Physical coordinate that a trajectory dimension runs along."""

    DISTANCE = "distance"
    ANGLE = "angle"
    DIHEDRAL = "dihedral"
    OTHER = "other"
    """Not measurable from the geometry (e.g. an IRC arc length)."""

    @property
    def key_count(self) -> int | None:
        """Number of atom keys defining the coordinate, or `None` for `OTHER`."""
        return {"distance": 2, "angle": 3, "dihedral": 4}.get(self.value)

    @property
    def default_units(self) -> str:
        """Units that values are stored in unless the axis says otherwise."""
        return {"distance": "angstrom", "other": "dimensionless"}.get(
            self.value, "degree"
        )
