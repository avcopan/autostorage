"""Calculation models."""

from typing import TYPE_CHECKING, Any

from automatics import Calculation
from sqlalchemy.types import JSON
from sqlmodel import Column, Field, Relationship

from .base import BaseRow
from .geom import InputGeometryLink

if TYPE_CHECKING:
    from .geom import GeometryRow, StationaryPointRow, TrajectoryRow


class CalculationRow(BaseRow, Calculation, table=True):
    r"""Calculation input parameters and metadata.

    Attributes
    ----------
    program : str
        Quantum chemistry program used (psi4, ORCA, ...)
    calc_type : str
        Calculation type (energy, optimization, ...)
    method : str, optional
        Computational method (B3LYP, MP2, ...)
    basis : str, optional
        Basis set.
    input_data : dict, optional
        Dictionary containing optional calculation parameters.
    provenance_source : str, optional
        Original producer of the provenance data.
    provenance : dict, optional
        Dictionary containing optional provenance data.
    base_hash : str, optional
        Auto-populated attribute hashing base Calculation attributes.
    full_hash : str, optional
        Auto-populated attribute hashing base Calculation attributes and input_data.

    Example
    -------
    ```
    calc = Calculation(
        program = "orca",
        calc_type = "optimization",
        method = "b3lyp",
        basis = "def2-SVP",
        input_data = {
            "inp": "%MAXCORE 4000%\nbase 'opt'\n! B3LYP OPT\n\n*xyzfile 0 2 inp.xyz\n"
        },
        provenance_source = "custom",
        provenance = {
            "program_version": "6.1.1",
            "aux_basis": "def2/J",
            "wall_time": "00:00:05:58",
        }
    )
    ```
    """

    __tablename__ = "calculation"
    id: int | None = Field(default=None, primary_key=True)

    # Have to redeclare these fields for sql type verification.
    input_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    provenance: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    input_geometries: list["GeometryRow"] = Relationship(
        back_populates="calculation_inputs", link_model=InputGeometryLink
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )
    trajectories: list["TrajectoryRow"] = Relationship(back_populates="calculation")


class EnergyRow(BaseRow, table=True):
    """
    Results of an energy calculation for a specific geometry.

    Attributes
    ----------
    geometry_id
        Foreign key to the specific geometry.
    calculation_id
        Foreign key to the calculation that produced this energy.
    value
        Energy value in Hartree.
    [SQL] geometry
        GeometryRow defining the point's coordinates.
    [SQL] calculation
        Parent CalculationRow.
    """

    __tablename__ = "energy"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )
    value: float

    calculation: "CalculationRow" = Relationship(back_populates="energies")
    geometry: "GeometryRow" = Relationship(back_populates="energies")
