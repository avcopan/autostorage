"""Calculation models."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from qcdata import CalcType
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship

from ..calcn import Calculation
from ..types import PathTypeDecorator, RowID
from .base import BaseRow
from .links import CalculationGeometryLink, CalculationTrajectoryLink

if TYPE_CHECKING:
    from .data import EnergyRow
    from .stationary import StationaryPointRow
    from .trajectory import TrajectoryRow


class CalculationRow(BaseRow, Calculation, table=True):
    """
    CalculationRow input parameters.

    Attributes
    ----------
    program
        Quantum chemistry program used (psi4, ORCA, ...)
    program_keywords
        (Optional) Quantum chemistry program keywords.
    super_program
        (Optional) Geometry optimizer program (geomeTRIC, ...).
    super_keywords
        (Optional) Geometry optimizer keywords.
    cmdline_args
        (Optional) Command line arguments.
    input
        (Optional) Input file. [ PLACEHOLDER ]
    files
        (Optional) Additional input files. [ PLACEHOLDER ]
    calc_type
        Calculation type (energy, optimization, ...)
    method
        Computational method (B3LYP, MP2, ...)
    basis
        (Optional) Basis set.
    [SQL] provenance
        Linked ProvenanceRow.
    [SQL] geometry_links
        List of linked CalculationGeometryLinks allowing access to Role directly.
    [SQL] hashes
        List of linked hashes.
    [SQL] energies
        List of linked energies.
    [SQL] stationary_points
        List of linked stationary points.
    [SQL] trajectories
        List of linked trajectories.
    """

    # - SQL Metadata ------------------
    __tablename__ = "calculation"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    # - Attributes --------------------
    # Have to redeclare these fields for sql type verification.
    program_keywords: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    super_keywords: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    cmdline_args: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # - SQLModel relationships --------
    provenance: "ProvenanceRow" = Relationship(back_populates="calculation")
    geometry_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="calculation"
    )
    hashes: list["CalculationHashRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )
    trajectories: list["TrajectoryRow"] = Relationship(
        back_populates="calculation", link_model=CalculationTrajectoryLink
    )

    # - Methods -----------------------
    @staticmethod
    def from_calculation(
        calc: Calculation, *, calc_type: CalcType | None = None
    ) -> "CalculationRow":
        """
        Instantiate CalculationRow from Calculation.

        Returns
        -------
        CalculationRow
        """
        calc_row = CalculationRow(**calc.model_dump(exclude_defaults=True))
        if calc_type:
            calc_row.calc_type = calc_type
        return calc_row


class ProvenanceRow(BaseRow, table=True):
    """
    CalculationRow metadata.

    Parameters
    ----------
    program_version
        (Optional) Program version.
    super_version
        (Optional) Superprogram version, if applicable.
    input
        (Optional) Input file.
    files
        (Optional) Additional input files.
    scratch_dir
        (Optional) Working directory.
    wall_time
        (Optional) Compute wall time.
    host_name
        (Optional) Name of host machine.
    host_cpus
        (Optional) Number of CPUs on host machine.
    host_mem
        (Optional) Amount of memory on host machine.
    extras
        (Optional) Additional calculation metadata.
    [SQL] calculation
        Linked CalculationRow.
    """

    # - SQL Metadata ------------------
    __tablename__ = "provenance"
    # - Row id ------------------------
    # - Foreign keys ------------------
    calculation_id: RowID | None = Field(
        primary_key=True,
        default=None,
        foreign_key="calculation.id",
        index=True,
        nullable=False,
        ondelete="CASCADE",
    )
    # - Attributes --------------------
    program_version: str | None = Field(default=None)
    super_version: str | None = Field(default=None)
    input: str | None = Field(default=None)
    files: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    scratch_dir: Path | None = Field(default=None, sa_column=Column(PathTypeDecorator))
    wall_time: float | None = Field(default=None)
    host_name: str | None = Field(default=None)
    host_cpus: int | None = Field(default=None)
    host_mem: int | None = Field(default=None)
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # - SQLModel relationships --------
    calculation: CalculationRow = Relationship(back_populates="provenance")


class CalculationHashRow(BaseRow, table=True):
    """
    Hash value for a calculation for identification and deduplication.

    Attributes
    ----------
    calculation_id
        Foreign key to the parent CalculationRow.
    name
        Type of hash (e.g., 'minimal', 'full').
    value
        The 64-character hash string.
    [SQL] calculation
        The parent CalculationRow.
    """

    # - SQL Metadata ------------------
    __tablename__ = "calculation_hash"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    calculation_id: RowID = Field(
        foreign_key="calculation.id", index=True, nullable=False, ondelete="CASCADE"
    )
    # - Attributes --------------------
    name: str = Field(index=True)
    value: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    # - SQLModel relationships --------
    calculation: CalculationRow = Relationship(back_populates="hashes")
