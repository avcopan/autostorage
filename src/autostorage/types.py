"""Autostorage types."""

import zlib
from enum import StrEnum
from io import BytesIO
from typing import Any

import numpy as np
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

__all__ = [
    "CalcType",
    "CompressedArrayTypeDecorator",
    "Role",
]


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


class CalcType(StrEnum):
    """Primary calculation types.

    Attributes
    ----------
    OPT
        Geometry optimization to find a local minimum on the PES.
    OPT_TS
        Saddle-point geometry optimization to locate a transition state structure.
    CONFORMER
        Conformational search/sampling to identify low-energy spatial arrangements.
    SCAN
        PES scan across user-defined geometric coordinates.
    IRC
        Intrinsic Reaction Coordinate mapping minimum energy pathway from TS to
        its connected reactants and products.
    MEP
        Minimum Energy Path multi-image chain searches (e.g., Nudged Elastic Band,
        String Methods) to discover reaction trajectories and TS guesses.
    ENERGY
        Single-point electronic energy evaluation at a fixed molecular geometry.
    GRADIENT
        Nuclear gradient evaluation to compute forces acting on the atoms.
    FREQUENCY
        Vibrational frequency analysis to verify stationary point order and compute
        a Hessian/zero-point energy.
    THERMO
        Statistical mechanics/thermochemical parsing to determine enthalpy (`H`),
        entropy (`S`), and Gibbs free energy (`G`).
    UNDEFINED
        Placeholder for generic or unclassified calculation types.
    """

    # Structural exploration
    OPT = "optimization"
    OPT_TS = "transition_optimization"
    CONFORMER = "conformer_search"
    # Path generation
    SCAN = "scan"
    IRC = "intrinsic_reaction_coordinate"
    MEP = "minimum_energy_path_search"
    # Properties
    ENERGY = "energy"
    GRADIENT = "gradient"
    FREQUENCY = "frequency"
    THERMO = "thermochemistry"
    # Fallback
    UNDEFINED = "undefined"
