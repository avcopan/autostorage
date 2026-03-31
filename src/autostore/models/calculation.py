"""Calculation row model and associated models and functions."""

from typing import TYPE_CHECKING

from sqlalchemy.types import String
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from ..calcn import Calculation

if TYPE_CHECKING:
    from .data import EnergyRow
    from .stationary import StationaryPointRow


class CalculationRow(Calculation, SQLModel, table=True):
    """
    Calculation metadata table row.

    Parameters
    ----------
    id
        Primary key.
    program
        The quantum chemistry program used (e.g., ``"Psi4"``, ``"Gaussian"``).
    method
        Computational method (e.g., ``"B3LYP"``, ``"MP2"``).
    basis
        Basis set, if applicable.
    input
        Input file for the calculation, if applicable.
    keywords
        QCIO keywords for the calculation.
    cmdline_args
        Command line arguments for the calculation.
    files
        Additional files required for the calculation.
    calctype
        Type of calculation (e.g., ``"energy"``, ``"gradient"``, ``"hessian"``).
    program_version
        Version of the quantum chemistry program.
    scratch_dir
        Working directory.
    wall_time
        Wall time.
    hostname
        Name of host machine.
    hostcpus
        Number of CPUs on host machine.
    hostmem
        Amount of memory on host machine.
    extras
        Additional metadata for the calculation.
    energy
        Relationship to the associated energy record, if present.
    hashes
        Relationship to the associated hash records, if present.
    stationary_point
        Relationship to the associated stationary point records, if present.
    """

    __tablename__ = "calculation"

    id: int | None = Field(default=None, primary_key=True)
    # Have to redeclare these fields to bypass type inspection
    keywords: dict[str, str | dict | None] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    superprogram_keywords: dict[str, str | dict | None] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    cmdline_args: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )
    files: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    extras: dict[str, str | dict | None] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )

    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    hashes: list["CalculationHashRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )


class CalculationHashRow(SQLModel, table=True):
    """
    Hash value for a calculation.

    One row corresponds to one hash type applied to one calculation.
    """

    __tablename__ = "calculation_hash"

    id: int | None = Field(default=None, primary_key=True)
    calculation_id: int = Field(
        foreign_key="calculation.id", index=True, nullable=False, ondelete="CASCADE"
    )

    name: str = Field(index=True)
    value: str = Field(sa_column=Column(String(64), index=True, nullable=False))

    calculation: CalculationRow = Relationship(back_populates="hashes")
