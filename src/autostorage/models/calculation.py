"""Calculation models."""

from typing import TYPE_CHECKING, Any

from automatics import Model
from sqlmodel import JSON, Column, Field, Relationship, UniqueConstraint

from .base import BaseRow

if TYPE_CHECKING:
    from .geom import GeometryRow, StationaryPointRow, TrajectoryRow


class ModelRow(BaseRow, Model, table=True):
    r"""Calculation input parameters and metadata.

    Attributes
    ----------
    program : str
        Quantum chemistry program used (psi4, ORCA, ...)
    program_version : str, optional
        Quantum chemistry program version.
    calc_type : str
        Calculation type (energy, optimization, ...)
    method : str
        Computational method (B3LYP, MP2, ...)
    basis : str, optional
        Orbital basis set.

    Example
    -------
    ```
    opt_model = ModelRow(
        program = "orca",
        program_version = "6.1.1",
        calc_type = "optimization",
        method = "b3lyp",
        basis = "def2-SVP",
    )
    ```
    """

    __tablename__ = "model"
    id: int | None = Field(default=None, primary_key=True)
    __table_args__ = (
        UniqueConstraint(
            "program",
            "program_version",
            "calc_type",
            "method",
            "basis",
            name="uix_model_identity",
        ),
    )

    calculations: list["CalculationRow"] = Relationship(back_populates="model")


class CalculationRow(BaseRow, table=True):
    r"""Calculation input parameters and metadata.

    Attributes
    ----------
    model_id : int
        Foreign key to the calculation model.
    input_geometry_id : int, optional
        Foreign key to the input geometry.
    output_geometry_id : int, optional
        Foreign key to the output geometry.
    input_trajectory_id : int, optional
        Foreign key to the input trajectory.
    output_trajectory_id : int, optional
        Foreign key to the output trajectory.
    model : ModelRow
        Instance of the calculation model.
    input_geometry : GeometryRow, optional
        Instance of the input geometry.
    output_geometry : GeometryRow, optional
        Instance of the output geometry.
    input_trajectory : TrajectoryRow, optional
        Instance of the input trajectory.
    output_trajectory : TrajectoryRow, optional
        Instance of the output trajectory.
    provenance : ProvenanceRow, optional
        Instance of the calculation provenance.

    Example
    -------
    ```
    from autostorage import CalculationRow, ModelRow, GeometryRow, ProvenanceRow

    opt_model = ModelRow(
        program = "orca",
        program_version = "6.1.1",
        calc_type = "optimization",
        method = "b3lyp",
        basis = "def2-SVP",
    )

    inp_geo = GeometryRow(
        symbols=["H", "H"], coordinates=[[0,0,0], [0,0,0.7]], charge=0, spin=0
    )

    prov = ProvenanceRow(input={"geom": {"maxiter": 500}})

    opt_calc = CalculationRow(
        model = opt_model,
        input_geometry = inp_geo,
        provenance = prov,
    )

    out_geo, out_prov = ... # custom method for executing ORCA

    opt_calc.output_geometry = out_geo
    opt_calc.provenance.output = out_prov

    db.add(opt_calc)
    ```
    """

    __tablename__ = "calculation"
    id: int | None = Field(default=None, primary_key=True)

    model_id: int | None = Field(
        default=None, foreign_key="model.id", ondelete="CASCADE", nullable=False
    )
    input_geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE"
    )
    output_geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE"
    )
    input_trajectory_id: int | None = Field(
        default=None, foreign_key="trajectory.id", ondelete="CASCADE"
    )
    output_trajectory_id: int | None = Field(
        default=None, foreign_key="trajectory.id", ondelete="CASCADE"
    )

    model: "ModelRow" = Relationship(back_populates="calculations")
    input_geometry: "GeometryRow" = Relationship(
        back_populates="calculation_inputs",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_geometry_id]"},
    )
    output_geometry: "GeometryRow" = Relationship(
        back_populates="calculation_outputs",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.output_geometry_id]"},
    )
    input_trajectory: "TrajectoryRow" = Relationship(
        back_populates="calculation_inputs",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_trajectory_id]"},
    )
    output_trajectory: "TrajectoryRow" = Relationship(
        back_populates="calculation_outputs",
        sa_relationship_kwargs={
            "foreign_keys": "[CalculationRow.output_trajectory_id]"
        },
    )
    provenance: "ProvenanceRow" = Relationship(back_populates="calculation")
    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )


class ProvenanceRow(BaseRow, table=True):
    r"""Calculation input and output provenance.

    Attributes
    ----------
    calculation_id : int
        Foreign key to the calculation.
    input : dict[str, Any]
        Input provenance dictionary.
    output : dict[str, Any]
        Output provenance dictionary.
    calculation : CalculationRow
        Instance of the calculation.
    """

    __tablename__ = "provenance"

    calculation_id: int | None = Field(
        default=None,
        foreign_key="calculation.id",
        ondelete="CASCADE",
        primary_key=True,
        nullable=False,
    )

    input: dict[str, Any] | None = Field(default_factory=dict, sa_column=Column(JSON))
    output: dict[str, Any] | None = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship(back_populates="provenance")


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
