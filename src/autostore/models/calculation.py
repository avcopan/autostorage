"""Calculation models."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from qcdata import DualProgramInput, Model, ProgramInput, ProgramOutput
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship, SQLModel

from ..calcn import Calculation
from ..types import PathTypeDecorator, RowID
from .optional import PartialMixin

if TYPE_CHECKING:
    from .data import EnergyRow
    from .geometry import GeometryRow
    from .links import CalculationGeometryLink
    from .stationary import StationaryPointRow


class CalculationRow(PartialMixin, Calculation, SQLModel, table=True):
    """CalculationRow input parameters and metadata.

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

    SQLModel Relationships
    ----------------------
    provenance
        Linked ProvenanceRow.
    geometry_links
        List of linked CalculationGeometryLinks allowing access to Role directly.
    hashes
        List of linked hashes.
    energies
        List of linked energies.
    stationary_points
        List of linked stationary points.

    Methods
    -------
    from_calculation
        Convert Calculation to CalculationRow.
    calculation
        Convert CalculationRow to Calculation.
    program_input
        Convert CalculationRow to qcio program_input.
    from_program_output
        Convert qc ProgramOutput to CalculationRow.
        Instantiates and links ProvenanceRow.
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
        back_populates="calculation",
        sa_relationship_kwargs={"overlaps": "geometries"},
        cascade_delete=True,
    )  # overlaps acknowledges that we have a circular relationship
    hashes: list["CalculationHashRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )

    # - Methods -----------------------
    @staticmethod
    def from_calculation(calc: Calculation) -> "CalculationRow":
        """
        Instantiate CalculationRow from Calculation.

        Returns
        -------
        CalculationRow
        """
        return CalculationRow(**calc.model_dump(exclude_defaults=True))

    def calculation(self) -> Calculation:
        """
        Instantiate Calculation from CalculationRow.

        Returns
        -------
        Calculation
        """
        data = self.model_dump()

        # Calculation doesn't care about id
        if self.id:
            del [data.id]  # ty:ignore[unresolved-attribute]

        return Calculation(**data)

    def program_input(
        self, *, input_geo: "GeometryRow"
    ) -> DualProgramInput | ProgramInput:
        """
        Generate qcdata ProgramInput from Calculation and input Geometry.

        Parameters
        ----------
        input_geo
            Input GeometryRow.

        Returns
        -------
        qc DualProgramInput/ProgramInput
        """
        if self.super_program:
            return DualProgramInput.model_validate(
                {
                    "calctype": self.calc_type,
                    "structure": input_geo.structure(),
                    "keywords": self.super_keywords,
                    "subprogram": self.program,
                    "subprogram_args": {
                        "model": Model(method=self.method, basis=self.basis),
                        "keywords": self.program_keywords,
                        "cmdline_args": self.cmdline_args,
                    },
                }
            )

        return ProgramInput.model_validate(
            {
                "calctype": self.calc_type,
                "structure": input_geo.structure(),
                "model": Model(method=self.method, basis=self.basis),
                "keywords": self.program_keywords,
                "cmdline_args": self.cmdline_args,
            }
        )

    @staticmethod
    def from_program_output(prog_out: ProgramOutput) -> "CalculationRow":
        """
        Instantiate CalculationRow from qc ProgramOutput.

        **Automatically instantiates and relates ProvenanceRow.

        Parameters
        ----------
        prog_out
            qccompute ProgramOutput.

        Returns
        -------
        CalculationRow
            Validated calculation row.
        """
        prog_inp = prog_out.input_data
        provenance = prog_out.provenance

        if isinstance(prog_inp, DualProgramInput):
            data = {
                "program": prog_inp.subprogram,
                "program_keywords": prog_inp.subprogram_args.keywords,
                "super_program": provenance.program,
                "super_keywords": prog_inp.keywords,
                "cmdline_args": prog_inp.subprogram_args.cmdline_args,
                "calc_type": prog_inp.calctype.value,
                "method": prog_inp.subprogram_args.model.method,
                "basis": prog_inp.subprogram_args.model.basis,
            }

        else:
            data = {
                "program": provenance.program,
                "program_keywords": prog_inp.keywords,
                "cmdline_args": prog_inp.cmdline_args,
                "calc_type": prog_inp.calctype.value,
                "method": prog_inp.model.method,
                "basis": prog_inp.model.basis,
            }

        calc_row = CalculationRow.model_validate(data)
        calc_row.provenance = ProvenanceRow.from_program_output(prog_out)
        return calc_row


class ProvenanceRow(PartialMixin, SQLModel, table=True):
    """
    CalculationRow output parameters and metadata.

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

    @staticmethod
    def from_program_output(prog_out: ProgramOutput) -> "ProvenanceRow":
        """
        Instantiate ProvenanceRow from qc ProgramOutput.

        Parameters
        ----------
        prog_out
            qccompute ProgramOutput.

        Returns
        -------
        ProvenanceRow
            Validated provenance row.
        """
        prog_inp = prog_out.input_data
        provenance = prog_out.provenance
        data = prog_out.data

        if isinstance(prog_inp, DualProgramInput):
            traj_prov = [t.provenance for t in data.trajectory]
            data = {
                "program_version": traj_prov[0].program_version,
                "super_version": provenance.program_version,
                "input": None,  # Could be used to store .inp (or equivalent) files
                "files": {
                    "program": prog_inp.subprogram_args.files,
                    "super_program": prog_inp.files,
                },
                "scratch_dir": provenance.scratch_dir,
                "wall_time": provenance.wall_time,
                "host_name": provenance.hostname,
                "host_cpus": provenance.hostcpus,
                "host_mem": provenance.hostmem,
                "extras": {
                    "super_program": prog_inp.extras,
                    "program": prog_inp.subprogram_args.extras,
                },
            }

        else:
            data = {
                "program_version": provenance.program_version,
                "input": None,  # Could be used to store .inp (or equivalent) files
                "files": {"program": prog_inp.files},
                "scratch_dir": provenance.scratch_dir,
                "wall_time": provenance.wall_time,
                "host_name": provenance.hostname,
                "host_cpus": provenance.hostcpus,
                "host_mem": provenance.hostmem,
                "extras": {"program": prog_inp.extras},
            }

        return ProvenanceRow.model_validate(data)


class CalculationHashRow(PartialMixin, SQLModel, table=True):
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

    SQLModel Relationships
    ------------------------
    calculation
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
