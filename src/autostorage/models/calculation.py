"""Calculation models."""

from typing import TYPE_CHECKING, Any

import numpy as np
from automatics import Model, model
from automol import geom
from sqlalchemy import String, event
from sqlmodel import JSON, Column, Field, Relationship

from .base import BaseRow
from .geom import StepValidationLink

if TYPE_CHECKING:
    from .geom import GeometryRow, StationaryPointRow, StepRow, TrajectoryRow


class ModelRow(BaseRow, Model, table=True):
    """Quantum chemistry program and method parameters.

    Attributes
    ----------
    program : str
        Quantum chemistry program used (e.g. ``psi4``, ``orca``).
    program_version : str, optional
        Version string of the quantum chemistry program.
    calc_type : str
        Calculation type (e.g. ``energy``, ``optimization``).
    method : str
        Computational method (e.g. ``b3lyp``, ``mp2``).
    basis : str, optional
        Orbital basis set (e.g. ``def2-SVP``).
    calculations : list[CalculationRow]
        Calculations that use this model.

    Example
    -------
    ```python
        opt_model = ModelRow(
            program="orca",
            program_version="6.1.1",
            calc_type="optimization",
            method="b3lyp",
            basis="def2-SVP",
        )
    ```
    """

    __tablename__ = "model"
    id: int | None = Field(default=None, primary_key=True)

    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )

    calculations: list["CalculationRow"] = Relationship(back_populates="model")


class CalculationRow(BaseRow, table=True):
    """A single quantum chemistry calculation and its associated data.

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
    input_provenance : dict, optional
        Provenance metadata for the calculation inputs.
    output_provenance : dict, optional
        Provenance metadata for the calculation outputs.
    model : ModelRow
        The calculation model used.
    input_geometry : GeometryRow, optional
        Geometry passed as input to the calculation.
    output_geometry : GeometryRow, optional
        Geometry produced by the calculation.
    input_trajectory : TrajectoryRow, optional
        Trajectory passed as input to the calculation.
    output_trajectory : TrajectoryRow, optional
        Trajectory produced by the calculation.
    energies : list[EnergyRow]
        Energies associated with this calculation.
    gradients : list[GradientRow]
        Gradients associated with this calculation.
    hessians : list[HessianRow]
        Hessians associated with this calculation.
    stationary_points : list[StationaryPointRow]
        Stationary points identified by this calculation.

    Example
    -------
    ```python
    from autostorage import CalculationRow, ModelRow, GeometryRow

    opt_model = ModelRow(
        program="orca",
        program_version="6.1.1",
        calc_type="optimization",
        method="b3lyp",
        basis="def2-SVP",
    )

    inp_geo = GeometryRow(
        symbols=["H", "H"], coordinates=[[0, 0, 0], [0, 0, 0.7]], charge=0, spin=0
    )

    opt_calc = CalculationRow(
        model=opt_model,
        input_geometry=inp_geo,
        input_provenance={"geom": {"maxiter": 500}},
    )

    out_geo, out_prov = ...  # custom method for executing ORCA

    opt_calc.output_geometry = out_geo
    opt_calc.output_provenance = out_prov

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

    input_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    output_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
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
    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    gradients: list["GradientRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    hessians: list["HessianRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )
    validations: list["ValidationRow"] = Relationship(back_populates="calculation")


class EnergyRow(BaseRow, table=True):
    """Energy result for a specific geometry and calculation.

    Attributes
    ----------
    geometry_id : int
        Foreign key to the geometry this energy was evaluated at.
    calculation_id : int
        Foreign key to the calculation that produced this energy.
    value : float
        Energy value in Hartree.
    geometry : GeometryRow
        Geometry this energy was evaluated at.
    calculation : CalculationRow
        Calculation that produced this energy.
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


class GradientRow(BaseRow, table=True):
    """Energy gradient result for a specific geometry and calculation.

    Attributes
    ----------
    geometry_id : int
        Foreign key to the geometry this gradient was evaluated at.
    calculation_id : int
        Foreign key to the calculation that produced this gradient.
    value : list[float]
        Flattened gradient vector in Hartree/Bohr.
    geometry : GeometryRow
        Geometry this gradient was evaluated at.
    calculation : CalculationRow
        Calculation that produced this gradient.
    """

    __tablename__ = "gradient"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )

    value: list[float] = Field(sa_type=JSON)

    calculation: "CalculationRow" = Relationship(back_populates="gradients")
    geometry: "GeometryRow" = Relationship(back_populates="gradients")


class HessianRow(BaseRow, table=True):
    """Hessian result for a specific geometry and calculation.

    Attributes
    ----------
    geometry_id : int
        Foreign key to the geometry this Hessian was evaluated at.
    calculation_id : int
        Foreign key to the calculation that produced this Hessian.
    value : list[list[float]]
        Hessian matrix in Hartree/Bohr**2.
    geometry : GeometryRow
        Geometry this Hessian was evaluated at.
    calculation : CalculationRow
        Calculation that produced this Hessian.
    """

    __tablename__ = "hessian"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )

    value: list[list[float]] = Field(sa_type=JSON)

    calculation: "CalculationRow" = Relationship(back_populates="hessians")
    geometry: "GeometryRow" = Relationship(back_populates="hessians")
    stationary_point: "StationaryPointRow" = Relationship(back_populates="hessian")

    @property
    def harmonic_frequencies(self) -> tuple[float, ...]:
        """Harmonic frequencies derived from the Hessian."""
        freqs, _ = geom.vibrational_analysis(geo=self.geometry, hess=self.value)
        return freqs


class ValidationRow(BaseRow, table=True):
    """Validation result for a specific step and calculation.

    Attributes
    ----------
    calculation_id : int
        Foreign key to the calculation that performed this validation.
    method : str
        Type of validation step (e.g., ``irc``)
    extras : dict[str, Any]
        Additional metadata attached to this validation.
    calculation : CalculationRow
        Calculation that performed this validation.
    """

    __tablename__ = "validation"
    id: int | None = Field(default=None, primary_key=True)

    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE"
    )

    method: str
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship(back_populates="validations")
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )


@event.listens_for(ModelRow, "before_insert")
def ensure_model_hash(mapper, connection, target: ModelRow) -> None:  # noqa: ANN001, ARG001
    """Compute and assign the model hash before inserting a ModelRow."""
    if target is not None and target.hash is None:
        target.hash = model.model_hash(target)


@event.listens_for(GradientRow, "before_insert")
@event.listens_for(GradientRow, "before_update")
def verify_gradient_shape(mapper, connection, target: GradientRow) -> None:  # noqa: ANN001, ARG001
    """Verify shape of the Gradient array before saving to the database."""
    if not target.geometry:
        return

    expected = (3 * target.geometry.atom_count,)
    actual = np.shape(target.value)

    if actual != expected:
        msg = f"Gradient shape {actual} does not match expectation {expected}."
        raise ValueError(msg)


@event.listens_for(HessianRow, "before_insert")
@event.listens_for(HessianRow, "before_update")
def verify_hessian_shape(mapper, connection, target: HessianRow) -> None:  # noqa: ANN001, ARG001
    """Verify shape of the Hessian matrix before saving to DB."""
    if not target.geometry:
        return

    expected_dim = 3 * target.geometry.atom_count
    expected = (expected_dim, expected_dim)
    actual = np.shape(target.value)

    if actual != expected:
        msg = f"Hessian shape {actual} does not match expectation {expected}."
        raise ValueError(msg)
