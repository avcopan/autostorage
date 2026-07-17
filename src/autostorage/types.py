"""Autostorage types."""

from enum import StrEnum
from typing import Any

import numpy as np
from sqlalchemy import LargeBinary
from sqlalchemy.types import JSON, TypeDecorator

__all__ = [
    "CalcType",
    "FloatArrayTypeDecorator",
    "Role",
]


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


class Float32BytesTypeDecorator(TypeDecorator):
    """Stores a NumPy array as flat raw float32 binary data in the DB."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:  # noqa: ANN401, ARG002
        if value is not None:
            # Force conversion to float32 and extract raw byte buffer
            return np.asarray(value, dtype=np.float32).tobytes()
        return None

    def process_result_value(
        self,
        value: bytes | None,
        dialect: Any,  # noqa: ANN401, ARG002
    ) -> np.ndarray | None:
        if value is not None:
            # Read back as a flat 1D float32 array
            return np.frombuffer(value, dtype=np.float32)
        return None


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
