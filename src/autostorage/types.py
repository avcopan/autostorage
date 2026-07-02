"""Autostorage types."""

from enum import StrEnum
from pathlib import Path

import numpy as np
from sqlalchemy.types import JSON, String, TypeDecorator

TrajectoryIndices = list[int | list[int]]

__all__ = [
    "CalcType",
    "FloatArrayTypeDecorator",
    "PathTypeDecorator",
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
