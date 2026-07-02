"""Autostorage models."""

import hashlib
import json
from typing import TYPE_CHECKING, Any, Self, dataclass_transform

import numpy as np
from automol import Geometry, Identity, geom
from automol.utils.types import FloatArray
from pydantic import ConfigDict, model_validator
from sqlalchemy.exc import NoResultFound
from sqlmodel import (
    JSON,
    CheckConstraint,
    Column,
    Enum,
    Field,
    Relationship,
    SQLModel,
    String,
    UniqueConstraint,
    func,
    select,
)

from autostorage.exc import MissingPrimaryKeyError

from .types import CalcType, FloatArrayTypeDecorator, Role

if TYPE_CHECKING:
    from .database import Database


def hash_by_dict(data: dict[str, Any]) -> str:
    """Generate a determinate hash from dictionary entries."""
    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def row_hash(row: SQLModel, *, exclude: set[str] | None = None) -> str:
    """Generate a determinate BaseRow hash string.

    Parameters
    ----------
    row
        Instance of a BaseRow.
    exclude
        Fields to exclude from hash.

    Returns
    -------
    model hash
    """
    exclude = exclude | {"id", "hash"} if exclude else {"id", "hash"}
    data = {
        k: v.strip().lower() if isinstance(v, str) else v
        for k, v in row.model_dump(exclude=exclude).items()
    }

    return hash_by_dict(data)


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class BaseRow(SQLModel):
    """Base for models with a primary ID."""

    id: int | None = Field(default=None, primary_key=True)

    def save(self, db: "Database") -> Self:
        """Add (or merge) self into the session, returning tracked row."""
        if self.id is None:
            db.add(self)
        return db.merge(self)


class BaseHashedRow(BaseRow):
    """Base for hashed models."""

    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )

    def resolve(self, db: "Database") -> Self:
        """Return the existing DB row matching this row's hash, else self."""
        stmt = select(type(self)).where(type(self).hash == self.hash)
        try:
            return db.exec_one(stmt)
        except NoResultFound:
            return self


class BaseResultRow(BaseRow):
    """Base for result models."""

    geometry_id: int | None

    @classmethod
    def query(
        cls,
        db: "Database",
        *,
        geo: "GeometryRow",
        model: "ModelRow",
        prov: dict[Any, Any] | None = None,
    ) -> Self | None:
        """Query for result matching geometry, model, and provenance."""
        if not geo.id or not model.id:
            raise MissingPrimaryKeyError([geo, model])

        prov = prov or {}
        stmt = (
            select(cls)
            .join(CalculationRow)
            .where(
                cls.geometry_id == geo.id,
                CalculationRow.model_id == model.id,
                CalculationRow.input_provenance == prov,
            )
        )
        return db.exec_first(stmt)


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class BaseLink(SQLModel):
    """Base for models without a primary ID."""

    def save(self, db: "Database") -> Self:
        """Add (or merge) self into the session.

        Returns None to discourage duplicate inserts of joint PK.
        """
        db.add(self)
        return self


# Link tables
class CalculationGeometryLink(BaseLink, table=True):
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
        The linked geometry.
    calculation
        The linked calculation.
    """

    __tablename__ = "calculation_geometry_link"

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
    role: Role = Field(sa_column=Column(Enum(Role)))

    geometry: "GeometryRow" = Relationship(back_populates="calculation_links")
    calculation: "CalculationRow" = Relationship(back_populates="geometry_links")


class CalculationTrajectoryLink(BaseLink, table=True):
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
        The linked trajectory.
    calculation
        The linked calculation.
    """

    __tablename__ = "calculation_trajectory_link"

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
    role: Role = Field(sa_column=Column(Enum(Role)))

    trajectory: "TrajectoryRow" = Relationship(back_populates="calculation_links")
    calculation: "CalculationRow" = Relationship(back_populates="trajectory_links")


class TrajectoryGeometryLink(BaseLink, table=True):
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
        The linked geometry.
    trajectory
        The linked trajectory.
    """

    __tablename__ = "trajectory_geometry_link"

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


class StationaryIdentityLink(BaseLink, table=True):
    """Association table linking stationary points to chemical identities.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    identity_id
        Foreign key to the linked identity.
    """

    __tablename__ = "stationary_identity_link"

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


class StationaryStageLink(BaseLink, table=True):
    """Association table linking stationary points to reaction stages.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    stage_id
        Foreign key to the linked reaction stage.
    stationary
        The linked stationary point.
    stage
        The linked reaction stage.
    """

    __tablename__ = "stationary_stage_link"

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


class StepValidationLink(BaseLink, table=True):
    """Association table linking validations to a step.

    Attributes
    ----------
    step_id
        Foreign key to the linked step.
    validation_id
        Foreign key to the linked validation.
    """

    __tablename__ = "step_validation_link"

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


# Result tables
class EnergyRow(BaseResultRow, table=True):
    """Energy result for a specific geometry and calculation.

    Attributes
    ----------
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

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )
    value: float

    calculation: "CalculationRow" = Relationship()
    geometry: "GeometryRow" = Relationship(back_populates="energies")


class GradientRow(BaseResultRow, table=True):
    """Energy gradient result for a specific geometry and calculation.

    Attributes
    ----------
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
    model_config = ConfigDict(arbitrary_types_allowed=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )
    value: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))

    calculation: "CalculationRow" = Relationship()
    geometry: "GeometryRow" = Relationship(back_populates="gradients")


class HessianRow(BaseResultRow, table=True):
    """Hessian result for a specific geometry and calculation.

    Attributes
    ----------
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
    model_config = ConfigDict(arbitrary_types_allowed=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )

    value: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))

    calculation: "CalculationRow" = Relationship()
    geometry: "GeometryRow" = Relationship(back_populates="hessians")

    @property
    def harmonic_frequencies(self) -> tuple[float, ...]:
        """Harmonic frequencies derived from the Hessian."""
        freqs, _ = geom.vibrational_analysis(geo=self.geometry, hess=self.value)
        return freqs

    @property
    def order(self) -> int:
        """Hessian order."""
        return sum(1 for f in self.harmonic_frequencies if f < 0.0)


# Geometry table
class GeometryRow(BaseHashedRow, Geometry, table=True):
    """Molecular geometry definition and metadata.

    Attributes
    ----------
    symbols
        Atomic symbols in order.
    coordinates
        Atomic coordinates in Angstrom.
    charge
        Total molecular charge.
    spin
        Number of unpaired electrons (2S).
    hash
        Unique hash of the geometry used for deduplication.
    """

    __tablename__ = "geometry"

    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))
    charge: int
    spin: int

    energies: list["EnergyRow"] = Relationship(back_populates="geometry")
    gradients: list["GradientRow"] = Relationship(back_populates="geometry")
    hessians: list["HessianRow"] = Relationship(back_populates="geometry")
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry"
    )
    trajectory_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="geometry"
    )
    calculation_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="geometry"
    )

    def calculation_link(
        self: Self, calc: "CalculationRow", role: Role
    ) -> CalculationGeometryLink:
        """Return a CalculationGeometryLink to self."""
        return CalculationGeometryLink(calculation=calc, geometry=self, role=role)

    def trajectory_link(
        self: Self, traj: "TrajectoryRow", index: list[int] | None = None
    ) -> TrajectoryGeometryLink:
        """Return a TrajectoryGeometryLink to self."""
        return TrajectoryGeometryLink(trajectory=traj, geometry=self, index=index)

    def stationary_point(
        self: Self,
        calc: "CalculationRow",
        *,
        order: int = 0,
        is_pseudo: bool = False,
        is_valid: bool = False,
    ) -> "StationaryPointRow":
        """Return a StationaryPointRow linked to self."""
        return StationaryPointRow(
            calculation=calc,
            geometry=self,
            order=order,
            is_pseudo=is_pseudo,
            is_valid=is_valid,
        )

    def energy(self: Self, calc: "CalculationRow", value: float) -> "EnergyRow":
        """Return an EnergyRow linked to self."""
        return EnergyRow(calculation=calc, geometry=self, value=value)

    def gradient(
        self: Self, calc: "CalculationRow", value: list[float]
    ) -> "GradientRow":
        """Return a GradientRow linked to self."""
        return GradientRow(calculation=calc, geometry=self, value=np.array(value))

    def hessian(
        self: Self, calc: "CalculationRow", value: list[list[float]]
    ) -> "HessianRow":
        """Return a HessianRow linked to self."""
        return HessianRow(calculation=calc, geometry=self, value=np.array(value))


# Trajectory table
class TrajectoryRow(BaseRow, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes
    ----------
    geometry_links
        Raw link rows connecting geometries to this trajectory.
    """

    __tablename__ = "trajectory"

    geometry_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="trajectory"
    )
    calculation_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )

    def geometry_link(
        self: Self, geo: "GeometryRow", index: list[int] | None = None
    ) -> TrajectoryGeometryLink:
        """Return a TrajectoryGeometryLink to self."""
        return TrajectoryGeometryLink(trajectory=self, geometry=geo, index=index)

    def calculation_link(
        self: Self, calc: "CalculationRow", role: Role
    ) -> CalculationTrajectoryLink:
        """Return a CalculationTrajectoryLink to self."""
        return CalculationTrajectoryLink(calculation=calc, trajectory=self, role=role)


# Stationary point rows
class StationaryPointRow(BaseRow, table=True):
    """A stationary point on a potential energy surface.

    Attributes
    ----------
    geometry_id
        Foreign key to the underlying molecular geometry.
    calculation_id
        Foreign key to the calculation that identified this point.
    order
        Hessian index (0 for minima, 1 for first-order saddle points).
    is_pseudo
        Whether this point is not a true stationary point (e.g. constrained).
    geometry
        Geometry defining the coordinates of this point.
    calculation
        Calculation that identified this point.
    identities
        Chemical identifiers (e.g. InChI, SMILES) for this point.
    stage_links
        Raw link rows connecting this stationary point to reaction stages.
    """

    __tablename__ = "stationary_point"

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )
    order: int = 0
    is_pseudo: bool = False
    is_valid: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship()
    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryIdentityLink
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationaries", link_model=StationaryStageLink
    )

    @classmethod
    def query(
        cls,
        db: "Database",
        *,
        ident: Identity,
        model: "ModelRow | None" = None,
        prov: dict[Any, Any] | None = None,
        calc_type: CalcType | None = None,
    ) -> Self | None:
        """Query for stationary point matching geometry, model, and provenance."""
        stmt = (
            select(cls)
            .join(
                StationaryIdentityLink,
                cls.id == StationaryIdentityLink.stationary_id,  # ty:ignore[invalid-argument-type]
            )
            .join(
                IdentityRow,
                IdentityRow.id == StationaryIdentityLink.identity_id,  # ty:ignore[invalid-argument-type]
            )
            .where(
                IdentityRow.kind == ident.kind,
                IdentityRow.algorithm == ident.algorithm,
                IdentityRow.value == ident.value,
            )
        )

        if model or prov or calc_type:
            stmt = stmt.join(
                CalculationRow,
                cls.calculation_id == CalculationRow.id,  # ty:ignore[invalid-argument-type]
            )

        if model:
            if not model.id:
                raise MissingPrimaryKeyError([model])
            stmt = stmt.where(CalculationRow.model_id == model.id)

        if prov:
            stmt = stmt.where(CalculationRow.input_provenance == prov)

        if calc_type:
            stmt = stmt.where(CalculationRow.calc_type == calc_type)

        return db.exec_first(stmt)


class IdentityRow(BaseRow, Identity, table=True):
    """A chemical identifier associated with one or more stationary points.

    Attributes
    ----------
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

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )
    identity_extras: list["IdentityExtraRow"] = Relationship(back_populates="identity")


class IdentityExtraRow(BaseRow, table=True):
    """Additional key-value metadata attached to a chemical identity.

    Attributes
    ----------
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

    identity_id: int | None = Field(
        default=None, foreign_key="identity.id", ondelete="CASCADE", nullable=False
    )

    attribute: str
    value: str

    identity: "IdentityRow" = Relationship(back_populates="identity_extras")


# Reaction rows
class StageRow(BaseRow, table=True):
    """A chemical state (reactant, product, or transition state) in a reaction.

    Attributes
    ----------
    is_ts
        Whether this stage represents a transition state.
    step_links
        Raw link rows connecting this stage to reaction steps, tagged by role.
    stationary_links
        Raw link rows connecting this stage to stationary points.
    """

    __tablename__ = "stage"

    is_ts: bool = False

    stationaries: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StationaryStageLink
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

    @classmethod
    def query(
        cls,
        db: "Database",
        stationaries: list["StationaryPointRow"],
        *,
        is_ts: bool = False,
    ) -> Self | None:
        """Query for existing stage with stationaries."""
        target_ids = [s.id for s in stationaries]
        if len(target_ids) != len(stationaries):
            raise MissingPrimaryKeyError(list(stationaries))

        stmt = (
            select(cls)
            .join(StationaryStageLink)
            .where(cls.is_ts == is_ts)
            .group_by(cls.id)  # ty:ignore[invalid-argument-type]
            .having(
                func.count(StationaryStageLink.stationary_id) == len(target_ids),  # ty:ignore[invalid-argument-type]
                func.count(
                    func.nullif(
                        StationaryStageLink.stationary_id.in_(target_ids),  # ty:ignore[unresolved-attribute]
                        False,  # noqa: FBT003
                    )
                )
                == len(target_ids),
            )
        )

        return db.exec_first(stmt)


class StepRow(BaseRow, table=True):
    """An elementary reaction step connecting a reactant, transition state, and product.

    Attributes
    ----------
    is_barrierless
        Whether this step proceeds without a formal transition state.
    validations
        Validation calculations performed on this step.
    """

    __tablename__ = "step"
    __table_args__ = (
        UniqueConstraint(
            "stage_id1", "stage_id2", "stage_id_ts", name="unq_step_stages"
        ),
        CheckConstraint("stage_id1 < stage_id2", name="chk_stage_order"),
    )

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

    @classmethod
    def query(
        cls,
        db: "Database",
        stage1: "StageRow",
        stage2: "StageRow",
        stage_ts: "StageRow | None" = None,
    ) -> Self | None:
        """Query for an existing step connecting specific stages."""
        if not stage1.id or not stage2.id or (stage_ts and not stage_ts.id):
            raise MissingPrimaryKeyError(
                [s for s in [stage1, stage2, stage_ts] if s is not None]
            )

        # Enforce the database CheckConstraint: stage_id1 < stage_id2
        id1, id2 = sorted([stage1.id, stage2.id])
        ts_id = stage_ts.id if stage_ts else None

        stmt = select(cls).where(
            cls.stage_id1 == id1,
            cls.stage_id2 == id2,
            cls.stage_id_ts == ts_id,
        )

        return db.exec_first(stmt)


# Calculation rows
class ModelRow(BaseHashedRow, table=True):
    """Calculation model specification.

    Attributes
    ----------
    program
        Quantum chemistry program used (psi4, ORCA, ...)
    program_version
        Quantum chemistry program version.
    method
        Computational method (B3LYP, MP2, ...)
    basis
        Orbital basis set.
    """

    __tablename__ = "model"
    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    program: str
    program_version: str | None = None
    method: str
    basis: str | None = None
    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )

    @model_validator(mode="after")
    def set_hash(self) -> Self:
        """Populate hash after model validation."""
        object.__setattr__(self, "hash", row_hash(self))
        return self


class CalculationRow(BaseRow, table=True):
    """Quantum chemistry calculation and its associated data.

    Attributes
    ----------
    model_id
        Foreign key to the model used for this calculation.
    calc_type
        Type of calculation performed.
    input_provenance
        Metadata describing how the input was generated.
    output_provenance
        Metadata describing how the output was produced.
    model
        Model used for this calculation.
    geometry_links
        Raw link rows connecting geometries to this calculation.
    """

    __tablename__ = "calculation"

    model_id: int | None = Field(
        default=None, foreign_key="model.id", ondelete="CASCADE", nullable=False
    )
    calc_type: CalcType = Field(
        sa_column=Column(Enum(CalcType, values_callable=lambda x: [e.value for e in x]))
    )
    input_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    output_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=Column(JSON)
    )

    model: "ModelRow" = Relationship()
    geometry_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="calculation"
    )
    trajectory_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="calculation"
    )

    def geometry_link(
        self: Self, geo: "GeometryRow", role: Role
    ) -> CalculationGeometryLink:
        """Return a CalculationGeometryLink to self."""
        return CalculationGeometryLink(calculation=self, geometry=geo, role=role)

    def trajectory_link(
        self: Self, traj: "TrajectoryRow", role: Role
    ) -> CalculationTrajectoryLink:
        """Return a CalculationTrajectoryLink to self."""
        return CalculationTrajectoryLink(calculation=self, trajectory=traj, role=role)


class ValidationRow(BaseRow, table=True):
    """Validation result for a specific step and calculation.

    Attributes
    ----------
    calculation_id
        Foreign key to the calculation that performed this validation.
    method
        Type of validation step (e.g., ``irc``)
    extras
        Additional metadata attached to this validation.
    calculation
        Calculation that performed this validation.
    """

    __tablename__ = "validation"
    id: int | None = Field(default=None, primary_key=True)

    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE"
    )

    method: str
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship()
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )
