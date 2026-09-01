"""SQLModel row definitions for autostorage's schema."""

from typing import Any

import numpy as np
from automol import Geometry, Identity
from automol.utils.types import FloatArray
from pydantic import field_validator
from sqlmodel import (
    JSON,
    CheckConstraint,
    Column,
    Enum,
    Field,
    Index,
    Relationship,
    SQLModel,
    UniqueConstraint,
    text,
)
from sqlmodel.main import SQLModelConfig

from .types import (
    CompressedArrayTypeDecorator,
    CompressedJSONTypeDecorator,
    Role,
    _fk_field,
)


# 0. Link rows
# NOTE: Link tables are named by the two entities they connect, in alphabetical order.
class CalculationGeometryLink(SQLModel, table=True):
    """Association table linking geometries to a calculation.

    Attributes
    ----------
    geometry_id
        Foreign key to the linked geometry.
    calculation_id
        Foreign key to the linked calculation.
    role
        Role the geometry plays for this calculation (input/output).
    geometry
        The linked geometry (back-populated from `GeometryRow.calculation_links`).
    calculation
        The linked calculation (back-populated from `CalculationRow.geometry_links`).
    """

    __tablename__ = "calculation_geometry_link"
    __table_args__ = (
        # The composite primary key only serves lookups keyed by `geometry_id`
        # (its leading column); this adds a matching index for `calculation_id`.
        Index("ix_calculation_geometry_link_calculation_id", "calculation_id"),
    )

    geometry_id: int | None = Field(
        default=None,
        foreign_key="geometry.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    calculation_id: int | None = Field(
        default=None,
        foreign_key="calculation.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    role: Role = Field(
        sa_column=Column(Enum(Role, values_callable=lambda x: [e.value for e in x]))
    )

    geometry: "GeometryRow" = Relationship(back_populates="calculation_links")
    calculation: "CalculationRow" = Relationship(back_populates="geometry_links")


class GeometryTrajectoryLink(SQLModel, table=True):
    """Association table linking geometries to a trajectory.

    Attributes
    ----------
    geometry_id
        Foreign key to the linked geometry.
    trajectory_id
        Foreign key to the linked trajectory.
    index
        Position of the geometry within the trajectory.
    geometry
        The linked geometry (back-populated from `GeometryRow.trajectory_links`).
    trajectory
        The linked trajectory (back-populated from `TrajectoryRow.geometry_links`).
    """

    __tablename__ = "geometry_trajectory_link"
    __table_args__ = (
        Index("ix_geometry_trajectory_link_trajectory_id", "trajectory_id"),
    )

    geometry_id: int | None = Field(
        default=None,
        foreign_key="geometry.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    trajectory_id: int | None = Field(
        default=None,
        foreign_key="trajectory.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    index: list[int] | None = Field(default=None, sa_column=Column(JSON))

    geometry: "GeometryRow" = Relationship(back_populates="trajectory_links")
    trajectory: "TrajectoryRow" = Relationship(back_populates="geometry_links")


class CalculationTrajectoryLink(SQLModel, table=True):
    """Association table linking trajectories to a calculation.

    Attributes
    ----------
    trajectory_id
        Foreign key to the linked trajectory.
    calculation_id
        Foreign key to the linked calculation.
    role
        Role the trajectory plays for this calculation (input/output).
    trajectory
        The linked trajectory (back-populated from `TrajectoryRow.calculation_links`).
    calculation
        The linked calculation (back-populated from `CalculationRow.trajectory_links`).
    """

    __tablename__ = "calculation_trajectory_link"
    __table_args__ = (
        Index("ix_calculation_trajectory_link_calculation_id", "calculation_id"),
    )

    trajectory_id: int | None = Field(
        default=None,
        foreign_key="trajectory.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    calculation_id: int | None = Field(
        default=None,
        foreign_key="calculation.id",
        ondelete="CASCADE",
        nullable=False,
        primary_key=True,
    )
    role: Role = Field(
        sa_column=Column(Enum(Role, values_callable=lambda x: [e.value for e in x]))
    )

    trajectory: "TrajectoryRow" = Relationship(back_populates="calculation_links")
    calculation: "CalculationRow" = Relationship(back_populates="trajectory_links")


class StageStationaryLink(SQLModel, table=True):
    """Association table linking stationary points to reaction stages.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    stage_id
        Foreign key to the linked reaction stage.
    """

    __tablename__ = "stage_stationary_link"
    __table_args__ = (Index("ix_stage_stationary_link_stage_id", "stage_id"),)

    stationary_id: int | None = Field(
        default=None,
        foreign_key="stationary_point.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    stage_id: int | None = Field(
        default=None,
        foreign_key="stage.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )


class StepValidationLink(SQLModel, table=True):
    """Association table linking validations to a step.

    Attributes
    ----------
    step_id
        Foreign key to the linked step.
    validation_id
        Foreign key to the linked validation.

    Notes
    -----
    Relationships are managed bidirectionally via `ValidationRow.step` and
    `StepRow.validations` using this table's `link_model`.
    """

    __tablename__ = "step_validation_link"
    __table_args__ = (Index("ix_step_validation_link_validation_id", "validation_id"),)

    step_id: int = Field(
        foreign_key="step.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    validation_id: int = Field(
        foreign_key="validation.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )


class IdentityStationaryLink(SQLModel, table=True):
    """Association table linking chemical identities to stationary points.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    identity_id
        Foreign key to the linked chemical identity.

    Notes
    -----
    Relationships are managed bidirectionally via `StationaryPointRow.identities`
    and `IdentityRow.stationary_points` using this table's `link_model`.
    """

    __tablename__ = "identity_stationary_link"
    __table_args__ = (Index("ix_identity_stationary_link_identity_id", "identity_id"),)

    stationary_id: int = Field(
        foreign_key="stationary_point.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )
    identity_id: int = Field(
        foreign_key="identity.id",
        primary_key=True,
        ondelete="CASCADE",
        nullable=False,
    )


# 1. Existential data rows
class GeometryRow(SQLModel, Geometry, table=True):
    """Molecular geometry definition and metadata.

    Attributes
    ----------
    id
        Primary key.
    symbols
        Atomic symbols in order.
    coordinates
        Atomic coordinates in Angstrom.
    charge
        Total molecular charge.
    spin
        Number of unpaired electrons (2S).
    energies
        Energy results computed at this geometry.
    gradients
        Gradient results computed at this geometry.
    hessians
        Hessian results computed at this geometry.
    stationary_points
        Stationary points defined by this geometry.
    trajectory_links
        Raw link rows connecting this geometry to trajectories.
    calculation_links
        Raw link rows connecting this geometry to calculations.
    """

    __tablename__ = "geometry"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: int | None = Field(default=None, primary_key=True)
    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(CompressedArrayTypeDecorator()))
    charge: int
    spin: int

    energies: list["EnergyRow"] = Relationship(back_populates="geometry")
    gradients: list["GradientRow"] = Relationship(back_populates="geometry")
    hessians: list["HessianRow"] = Relationship(back_populates="geometry")
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry"
    )
    trajectory_links: list["GeometryTrajectoryLink"] = Relationship(
        back_populates="geometry"
    )
    calculation_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="geometry"
    )

    @field_validator("coordinates", mode="before")
    @classmethod
    def _validate_coordinates(cls, value: list[list[float]] | FloatArray) -> FloatArray:
        """Convert list to numpy array if needed."""
        if isinstance(value, list):
            return np.asarray(value, dtype=float)
        return value


class TrajectoryRow(SQLModel, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes
    ----------
    id
        Primary key.
    geometry_links
        Raw link rows connecting geometries to this trajectory.
    calculation_links
        Raw link rows connecting calculations to this trajectory.
    """

    __tablename__ = "trajectory"

    id: int | None = Field(default=None, primary_key=True)
    ndim: int | None = Field(default=None, nullable=True)

    geometry_links: list["GeometryTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )
    calculation_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )


class ModelRow(SQLModel, table=True):
    """Calculation model specification.

    Attributes
    ----------
    id
        Primary key.
    program
        Quantum chemistry program used (psi4, ORCA, ...)
    program_version
        Quantum chemistry program version.
    method
        Computational method (B3LYP, MP2, ...)
    basis
        Orbital basis set.
    keywords
        Additional keywords and options for the calculation.
    calculations
        Calculations performed using this model.
    """

    __tablename__ = "model"

    id: int | None = Field(default=None, primary_key=True)
    program: str
    program_version: str | None = None
    method: str
    basis: str | None = None
    keywords: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )

    calculations: list["CalculationRow"] = Relationship(back_populates="model")


class CalculationRow(SQLModel, table=True):
    """Quantum chemistry calculation and its associated data.

    Attributes
    ----------
    id
        Primary key.
    model_id
        Foreign key to the model used for this calculation.
    calc_type
        Type of calculation (energy, gradient, hessian, etc.).
    input_provenance
        Metadata describing how the input was generated.
    output_provenance
        Metadata describing how the output was produced.
    model
        Model used for this calculation.
    geometry_links
        Raw link rows connecting geometries to this calculation.
    trajectory_links
        Raw link rows connecting trajectories to this calculation.
    energies
        Energy results produced by this calculation.
    gradients
        Gradient results produced by this calculation.
    hessians
        Hessian results produced by this calculation.
    validations
        Validation results performed by this calculation.
    stationary_points
        Stationary points identified by this calculation.
    """

    __tablename__ = "calculation"

    id: int | None = Field(default=None, primary_key=True)
    model_id: int | None = Field(
        default=None,
        foreign_key="model.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )
    calc_type: str
    input_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    output_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )

    model: "ModelRow" = Relationship(back_populates="calculations")
    energies: list["EnergyRow"] = Relationship(back_populates="calculation")
    gradients: list["GradientRow"] = Relationship(back_populates="calculation")
    hessians: list["HessianRow"] = Relationship(back_populates="calculation")
    validations: list["ValidationRow"] = Relationship(back_populates="calculation")
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )
    geometry_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="calculation"
    )
    trajectory_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="calculation"
    )


class EnergyRow(SQLModel, table=True):
    """Energy result for a specific geometry and calculation.

    Attributes
    ----------
    id
        Primary key.
    geometry_id
        Foreign key to the geometry this energy was evaluated at.
    calculation_id
        Foreign key to the calculation that produced this energy.
    value
        Energy value in Hartree.
    geometry
        Geometry this energy was evaluated at.
    calculation
        Calculation that produced this energy.
    """

    __tablename__ = "energy"

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    value: float

    calculation: "CalculationRow" = Relationship(back_populates="energies")
    geometry: "GeometryRow" = Relationship(back_populates="energies")


class GradientRow(SQLModel, table=True):
    """Energy gradient result for a specific geometry and calculation.

    Attributes
    ----------
    id
        Primary key.
    geometry_id
        Foreign key to the geometry this gradient was evaluated at.
    calculation_id
        Foreign key to the calculation that produced this gradient.
    value
        Flattened gradient vector in Hartree/Bohr.
    geometry
        Geometry this gradient was evaluated at.
    calculation
        Calculation that produced this gradient.
    """

    __tablename__ = "gradient"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    value: FloatArray = Field(sa_column=Column(CompressedArrayTypeDecorator()))

    calculation: "CalculationRow" = Relationship(back_populates="gradients")
    geometry: "GeometryRow" = Relationship(back_populates="gradients")


class HessianRow(SQLModel, table=True):
    """Hessian result for a specific geometry and calculation.

    Attributes
    ----------
    id
        Primary key.
    geometry_id
        Foreign key to the geometry this Hessian was evaluated at.
    calculation_id
        Foreign key to the calculation that produced this Hessian.
    value
        Hessian matrix in Hartree/Bohr^2.
    geometry
        Geometry this Hessian was evaluated at.
    calculation
        Calculation that produced this Hessian.
    """

    __tablename__ = "hessian"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")

    value: np.ndarray = Field(
        sa_column=Column(CompressedArrayTypeDecorator(dtype=np.float32))
    )

    calculation: "CalculationRow" = Relationship(back_populates="hessians")
    geometry: "GeometryRow" = Relationship(back_populates="hessians")


class ValidationRow(SQLModel, table=True):
    """Validation result for a specific step and calculation.

    Attributes
    ----------
    id
        Primary key.
    calculation_id
        Foreign key to the calculation that performed this validation.
    method
        Type of validation step (e.g., ``irc``)
    extras
        Additional metadata attached to this validation.
    calculation
        Calculation that performed this validation.
    step
        Reaction step this validation belongs to.
    """

    __tablename__ = "validation"

    id: int | None = Field(default=None, primary_key=True)
    calculation_id: int | None = _fk_field("calculation.id")

    method: str
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship(back_populates="validations")
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )


# 2. Stationary point rows
class StationaryPointRow(SQLModel, table=True):
    """A stationary point on a potential energy surface.

    Attributes
    ----------
    id
        Primary key.
    geometry_id
        Foreign key to the underlying molecular geometry.
    calculation_id
        Foreign key to the calculation that identified this point.
    order
        Hessian index (0 for minima, 1 for first-order saddle points).
    is_pseudo
        Whether this point is not a true stationary point (e.g. constrained).
    is_validated
        Whether this stationary point has been validated (e.g., by Hessian calculation).
    geometry
        Geometry defining the coordinates of this point.
    calculation
        Calculation that identified this point.
    identities
        Chemical identifiers (e.g. InChI, SMILES) for this point.
    stages
        Reaction stages this stationary point belongs to.
    """

    __tablename__ = "stationary_point"

    id: int | None = Field(default=None, primary_key=True)
    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    order: int = 0
    is_pseudo: bool = False
    is_validated: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")
    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=IdentityStationaryLink
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationaries", link_model=StageStationaryLink
    )


# 3. Reaction network rows
class StageRow(SQLModel, table=True):
    """A chemical state (reactant, product, or transition state) in a reaction.

    Attributes
    ----------
    id
        Primary key.
    is_ts
        Whether this stage represents a transition state.
    stationaries
        Stationary points that make up this stage (bidirectional via
        `link_model=StageStationaryLink`).
    steps
        Reaction steps referencing this stage as `stage1`, `stage2`, or
        `stage_ts`. Read-only view derived from `StepRow`'s foreign keys;
        use `stage1`, `stage2`, `stage_ts` relationships on `StepRow` for
        writing.
    """

    __tablename__ = "stage"

    id: int | None = Field(default=None, primary_key=True)
    is_ts: bool = False

    stationaries: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StageStationaryLink
    )
    steps: list["StepRow"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "or_("
            "StageRow.id == StepRow.stage_id1, "
            "StageRow.id == StepRow.stage_id2, "
            "StageRow.id == StepRow.stage_id_ts"
            ")",
            "viewonly": True,
        }
    )


class StepRow(SQLModel, table=True):
    """An elementary reaction step connecting a reactant, transition state, and product.

    Attributes
    ----------
    id
        Primary key.
    stage_id1, stage_id2
        Foreign keys to the step's two non-TS stages (stored with
        `stage_id1 < stage_id2`).
    stage_id_ts
        Foreign key to the step's transition-state stage, or `None` for a
        barrierless step.
    is_barrierless
        Whether this step proceeds without a formal transition state.
    stage1
        The step's first non-TS stage (reactant or product).
    stage2
        The step's second non-TS stage (reactant or product).
    stage_ts
        The step's transition-state stage, or `None` if barrierless.
        Note: not back-populated from StageRow.steps (which is read-only).
    validations
        Validation calculations performed on this step.
    """

    __tablename__ = "step"
    __table_args__ = (
        UniqueConstraint(
            "stage_id1", "stage_id2", "stage_id_ts", name="unq_step_stages"
        ),
        CheckConstraint("stage_id1 < stage_id2", name="chk_stage_order"),
        # `unq_step_stages` doesn't catch duplicate barrierless steps (stage_id_ts
        # NULL), since SQL never treats NULL as equal to itself in a unique
        # constraint. This expression index closes that gap at the DB level.
        Index(
            "unq_step_stages_null_safe",
            "stage_id1",
            "stage_id2",
            text("coalesce(stage_id_ts, 0)"),
            unique=True,
        ),
        # `stage_id1` is already covered as the leading column of the two indexes
        # above, but is indexed explicitly here too for symmetry/clarity.
        Index("ix_step_stage_id1", "stage_id1"),
        Index("ix_step_stage_id2", "stage_id2"),
        Index("ix_step_stage_id_ts", "stage_id_ts"),
    )

    id: int | None = Field(default=None, primary_key=True)
    stage_id1: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
        nullable=False,
    )
    stage_id2: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
        nullable=False,
    )
    stage_id_ts: int | None = Field(
        default=None,
        foreign_key="stage.id",
        ondelete="CASCADE",
    )

    is_barrierless: bool = False

    validations: list["ValidationRow"] = Relationship(
        back_populates="step", link_model=StepValidationLink
    )

    stage1: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id1]"}
    )
    stage2: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id2]"}
    )
    stage_ts: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id_ts]"}
    )


# 4. Identity rows
class IdentityRow(SQLModel, Identity, table=True):
    """A chemical identifier associated with one or more stationary points.

    Attributes
    ----------
    id
        Primary key.
    kind
        Category of identifier (e.g. ``stereoisomer``, ``formula``).
    algorithm
        Method used to generate the identifier (e.g. ``rdkit inchi``, ``rdkit smiles``).
    value
        The resulting identifier string.
    stationary_points
        Stationary points sharing this identity.
    identity_extras
        Additional key-value metadata attached to this identity.
    """

    __tablename__ = "identity"
    __table_args__ = (
        UniqueConstraint("kind", "algorithm", "value", name="unique_identity"),
    )

    id: int | None = Field(default=None, primary_key=True)

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=IdentityStationaryLink
    )
    identity_extras: list["IdentityExtraRow"] = Relationship(back_populates="identity")
    algorithm_cache: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(CompressedJSONTypeDecorator())
    )


class IdentityExtraRow(SQLModel, table=True):
    """Additional key-value metadata attached to a chemical identity.

    Attributes
    ----------
    id
        Primary key.
    identity_id
        Foreign key to the parent identity.
    attribute
        Name of the extra attribute.
    value
        Value of the extra attribute.
    identity
        The parent identity this extra belongs to.
    """

    __tablename__ = "identity_extras"

    id: int | None = Field(default=None, primary_key=True)
    identity_id: int | None = Field(
        default=None,
        foreign_key="identity.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )

    attribute: str
    value: str

    identity: "IdentityRow" = Relationship(back_populates="identity_extras")
