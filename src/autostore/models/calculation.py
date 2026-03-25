"""Calculation row model and associated models and functions."""

from pathlib import Path
from typing import TYPE_CHECKING

from qcio import DualProgramInput, ProgramInput, Results
from sqlalchemy import event
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship, Session, SQLModel

from ..calcn import Calculation, calculation_hash, hash_registry
from ..types import PathTypeDecorator

if TYPE_CHECKING:
    from .data import EnergyRow
    from .stationary import StationaryPointRow


class CalculationRow(SQLModel, table=True):
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
    """

    __tablename__ = "calculation"

    id: int | None = Field(default=None, primary_key=True)
    # Input fields:
    program: str
    method: str
    basis: str | None = None
    input: str | None = None
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
    calctype: str | None = None
    program_version: str | None = None
    # Provenance fields:
    superprogram: str | None = None
    superprogram_version: str | None = None
    scratch_dir: Path | None = Field(default=None, sa_column=Column(PathTypeDecorator))
    wall_time: float | None = None
    hostname: str | None = None
    hostcpus: int | None = None
    hostmem: int | None = None
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
    stationary_point: "StationaryPointRow" = Relationship(back_populates="calculation")

    def to_calculation(self: "CalculationRow") -> Calculation:
        """Reconstruct Calculation object from row."""
        return Calculation(
            program=self.program,
            method=self.method,
            basis=self.basis,
            input=self.input,
            keywords=self.keywords,
            superprogram_keywords=self.superprogram_keywords,
            cmdline_args=self.cmdline_args,
            files=self.files,
            calctype=self.calctype,
            program_version=self.program_version,
            superprogram=self.superprogram,
            superprogram_version=self.superprogram_version,
            scratch_dir=self.scratch_dir,
            wall_time=self.wall_time,
            hostname=self.hostname,
            hostcpus=self.hostcpus,
            hostmem=self.hostmem,
            extras=self.extras,
        )

    @classmethod
    def from_results(cls, res: Results) -> "CalculationRow":
        """
        Instantiate a CalculationRow from a QCIO Results object.

        Parameters
        ----------
        res
            QCIO Results object.

        Returns
        -------
            CalculationRow instance.

        Raises
        ------
        NotImplementedError
            If instantiation from the given input data type is not implemented.
        """
        prog_input = res.input_data

        if isinstance(prog_input, DualProgramInput):
            return cls(
                program=prog_input.subprogram,
                method=prog_input.subprogram_args.model.method,
                basis=prog_input.subprogram_args.model.basis,
                input=None,  # Could store input file text here if desired
                keywords=prog_input.subprogram_args.keywords,
                superprogram_keywords=prog_input.keywords,
                cmdline_args=prog_input.cmdline_args,
                files=prog_input.files,
                calctype=prog_input.calctype,
                program_version=res.provenance.extras.get("versions", {}).get(
                    prog_input.subprogram
                ),  # NOTE: This is a placeholder for getting the subversion
                superprogram=res.provenance.program,
                superprogram_version=res.provenance.program_version,
                scratch_dir=res.provenance.scratch_dir,
                wall_time=res.provenance.wall_time,
                hostname=res.provenance.hostname,
                hostcpus=res.provenance.hostcpus,
                hostmem=res.provenance.hostmem,
                extras=res.input_data.extras,
            )

        if isinstance(prog_input, ProgramInput):
            return cls(
                program=res.provenance.program,
                method=prog_input.model.method,
                basis=prog_input.model.basis,
                input=None,  # Could store input file text here if desired
                keywords=prog_input.keywords,
                cmdline_args=prog_input.cmdline_args,
                files=prog_input.files,
                calctype=prog_input.calctype,
                program_version=res.provenance.program_version,
                scratch_dir=res.provenance.scratch_dir,
                wall_time=res.provenance.wall_time,
                hostname=res.provenance.hostname,
                hostcpus=res.provenance.hostcpus,
                hostmem=res.provenance.hostmem,
                extras=res.input_data.extras,
            )

        msg = f"Instantiation from {type(res.input_data)} not yet implemented."
        raise NotImplementedError(msg)


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


@event.listens_for(Session, "after_flush")
def populate_calculation_hashes(session, flush_context) -> None:  # noqa: ANN001, ARG001
    """Populate the 'minimal' hash for newly added CalculationRow objects."""
    available = set(hash_registry.available())

    for row in session.new:
        if not isinstance(row, CalculationRow):
            continue

        existing = {h.name for h in row.hashes}
        missing = available - existing
        if not missing:
            continue

        calc = row.to_calculation()

        for name in missing:
            value = calculation_hash(calc, name=name)

            session.add(
                CalculationHashRow(
                    calculation=row,
                    name=name,
                    value=value,
                )
            )
