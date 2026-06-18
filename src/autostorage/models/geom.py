"""Geometry models."""

from pathlib import Path
from typing import TYPE_CHECKING

from automatics import Identity
from automatics.utils.types import FloatArray
from automol import Geometry, geom
from pydantic import model_validator
from sqlalchemy import CheckConstraint, event, insert
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship, Session, select

from ..utils.types import FloatArrayTypeDecorator, TrajectoryIndices
from .base import BaseRow

if TYPE_CHECKING:
    from .calculation import (
        CalculationRow,
        EnergyRow,
        GradientRow,
        HessianRow,
        ValidationRow,
    )


class TrajectoryGeometryLink(BaseRow, table=True):
    """Association table linking geometries to a trajectory.

    Attributes
    ----------
    geometry_id : int
        Foreign key to the linked geometry.
    trajectory_id : int
        Foreign key to the linked trajectory.
    index : list[int], optional
        Position of the geometry within the trajectory.
    geometry : GeometryRow
        The linked geometry.
    trajectory : TrajectoryRow
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


class StationaryIdentityLink(BaseRow, table=True):
    """Association table linking stationary points to chemical identities.

    Attributes
    ----------
    stationary_id : int
        Foreign key to the linked stationary point.
    identity_id : int
        Foreign key to the linked identity.
    """

    __tablename__ = "stationary_identity_link"

    stationary_id: int = Field(
        foreign_key="stationary_point.id", primary_key=True, ondelete="CASCADE"
    )
    identity_id: int = Field(
        foreign_key="identity.id", primary_key=True, ondelete="CASCADE"
    )


class StationaryStageLink(BaseRow, table=True):
    """Association table linking stationary points to reaction stages.

    Attributes
    ----------
    stationary_id : int
        Foreign key to the linked stationary point.
    stage_id : int
        Foreign key to the linked reaction stage.
    """

    __tablename__ = "stationary_stage_link"

    stationary_id: int = Field(
        foreign_key="stationary_point.id", primary_key=True, ondelete="CASCADE"
    )
    stage_id: int = Field(foreign_key="stage.id", primary_key=True, ondelete="CASCADE")


class StepValidationLink(BaseRow, table=True):
    """Association table linking validations to a step.

    Attributes
    ----------
    step_id : int
        Foreign key to the linked step.
    validation_id : int
        Foreign key to the linked validation.
    step : StepRow
        The linked step.
    validation : ValidationRow
        The linked validation.
    """

    __tablename__ = "step_validation_link"

    step_id: int = Field(foreign_key="step.id", primary_key=True, ondelete="CASCADE")
    validation_id: int = Field(
        foreign_key="validation.id", primary_key=True, ondelete="CASCADE"
    )


class GeometryRow(BaseRow, Geometry, table=True):
    """Molecular geometry definition and metadata.

    Attributes
    ----------
    symbols : list[str]
        Atomic symbols in order.
    coordinates : FloatArray
        Atomic coordinates in Angstrom.
    charge : int
        Total molecular charge.
    spin : int
        Number of unpaired electrons (2S).
    hash : str, optional
        Unique hash of the geometry used for deduplication.
    calculation_inputs : list[CalculationRow]
        Calculations that used this geometry as input.
    calculation_outputs : list[CalculationRow]
        Calculations that produced this geometry.
    energies : list[EnergyRow]
        Energies evaluated at this geometry.
    gradients : list[GradientRow]
        Gradients evaluated at this geometry.
    hessians : list[HessianRow]
        Hessians evaluated at this geometry.
    stationary_points : list[StationaryPointRow]
        Stationary points associated with this geometry.
    trajectory_links : list[TrajectoryGeometryLink]
        Trajectory membership links for this geometry.
    """

    __tablename__ = "geometry"
    id: int | None = Field(default=None, primary_key=True)

    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))
    charge: int | None = Field(default=None, nullable=False)
    spin: int | None = Field(default=None, nullable=False)
    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )

    calculation_inputs: list["CalculationRow"] = Relationship(
        back_populates="input_geometry",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_geometry_id]"},
    )
    calculation_outputs: list["CalculationRow"] = Relationship(
        back_populates="output_geometry",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.output_geometry_id]"},
    )
    trajectory_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="geometry"
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry"
    )
    energies: list["EnergyRow"] = Relationship(back_populates="geometry")
    gradients: list["GradientRow"] = Relationship(back_populates="geometry")
    hessians: list["HessianRow"] = Relationship(back_populates="geometry")


class TrajectoryRow(BaseRow, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes
    ----------
    id : int, optional
        Primary key.
    ndim : int
        Dimensionality of the trajectory index (e.g. 1 for a linear scan).
    geometries : list[GeometryRow]
        Ordered list of geometries in this trajectory.
    geometry_links : list[TrajectoryGeometryLink]
        Raw link rows connecting geometries to this trajectory.
    calculation_inputs : list[CalculationRow]
        Calculations that used this trajectory as input.
    calculation_outputs : list[CalculationRow]
        Calculations that produced this trajectory.
    """

    __tablename__ = "trajectory"
    id: int | None = Field(default=None, primary_key=True)

    ndim: int = 0

    @property
    def geometries(self) -> list["GeometryRow"]:
        """Linked geometries."""
        return [
            link.geometry
            for link in sorted(
                self.geometry_links,
                key=lambda link: link.index if link.index is not None else [],
            )
        ]

    @geometries.setter
    def geometries(self, value: list["GeometryRow"]) -> None:
        """Set linked geometries."""
        self.geometry_links = [TrajectoryGeometryLink(geometry=geom) for geom in value]

    @classmethod
    def from_geometries(
        cls, geos: list["GeometryRow"], indices: TrajectoryIndices | None = None
    ) -> "TrajectoryRow":
        """Instantiate TrajectoryRow from geometries with optional indices."""
        links: list[TrajectoryGeometryLink] = []
        ndim = 0

        if indices is not None:
            normalized_indices: list[list[int]] = [
                [item] if isinstance(item, int) else item for item in indices
            ]
            if len(normalized_indices) != len(geos):
                msg = "The number of indices must match the number of geometries."
                raise ValueError(msg)

            if normalized_indices:
                ndim = len(normalized_indices[0])
        else:
            normalized_indices = None

        for i, geo in enumerate(geos):
            idx = normalized_indices[i] if normalized_indices is not None else None
            links.append(TrajectoryGeometryLink(geometry=geo, index=idx))

        return cls(geometry_links=links, ndim=ndim)

    @classmethod
    def from_xyz_block(
        cls,
        xyz_block: str,
        indices: TrajectoryIndices | None = None,
        *,
        charge: int | None = None,
        spin: int | None = None,
    ) -> "TrajectoryRow":
        """Instantiate GeometryRow from a formatted xyz block."""
        lines = xyz_block.splitlines()

        natoms = int(lines[0])
        block_size: int = natoms + 2
        nblocks = int(len(lines) / block_size)

        geos = []

        for i in range(nblocks):
            start = block_size * i
            end = block_size * (i + 1)
            xyz_block = "\n".join(lines[start:end])
            geo = GeometryRow.from_xyz_block(xyz_block, charge=charge, spin=spin)

            if geo.atom_count != natoms:
                msg = "Failed to read trajectory from xyz block."
                raise ValueError(msg)

            geos.append(geo)

        return cls.from_geometries(geos, indices=indices)

    @classmethod
    def from_xyz_file(
        cls,
        path: str | Path,
        indices: TrajectoryIndices | None = None,
        *,
        charge: int | None = None,
        spin: int | None = None,
    ) -> "TrajectoryRow":
        """Instantiate GeometryRow from a formatted xyz block."""
        path = Path(path)
        return cls.from_xyz_block(
            path.read_text(), indices=indices, charge=charge, spin=spin
        )

    calculation_inputs: list["CalculationRow"] = Relationship(
        back_populates="input_trajectory",
        sa_relationship_kwargs={"foreign_keys": "[CalculationRow.input_trajectory_id]"},
    )
    calculation_outputs: list["CalculationRow"] = Relationship(
        back_populates="output_trajectory",
        sa_relationship_kwargs={
            "foreign_keys": "[CalculationRow.output_trajectory_id]"
        },
    )
    geometry_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="trajectory"
    )


class StationaryPointRow(BaseRow, table=True):
    """A stationary point on a potential energy surface.

    Attributes
    ----------
    geometry_id : int
        Foreign key to the underlying molecular geometry.
    calculation_id : int
        Foreign key to the calculation that identified this point.
    order : int
        Hessian index (0 for minima, 1 for first-order saddle points).
    is_pseudo : bool
        Whether this point is not a true stationary point (e.g. constrained).
    geometry : GeometryRow
        Geometry defining the coordinates of this point.
    calculation : CalculationRow
        Calculation that identified this point.
    identities : list[IdentityRow]
        Chemical identifiers (e.g. InChI, SMILES) for this point.
    stages : list[StageRow]
        Reaction stages this stationary point belongs to.
    """

    __tablename__ = "stationary_point"
    id: int | None = Field(default=None, primary_key=True)

    geometry_id: int | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE", nullable=False
    )
    calculation_id: int | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE", nullable=False
    )
    hessian_id: int | None = Field(default=None, foreign_key="hessian.id")

    order: int = 0
    is_pseudo: bool = False
    is_valid: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")
    hessian: "HessianRow" = Relationship(back_populates="stationary_point")

    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryIdentityLink
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryStageLink
    )

    @model_validator(mode="after")
    def valid_hessian(self) -> None:
        """Validate that a Hessian is provided if marking stationary point as valid."""
        if self.is_valid and not (self.hessian_id or self.hessian):
            msg = "StationaryPoint cannot be valid without an associated Hessian."
            raise ValueError(msg)


class IdentityRow(BaseRow, Identity, table=True):
    """A chemical identifier associated with one or more stationary points.

    Attributes
    ----------
    kind : str
        Category of identifier (e.g. ``stereoisomer``, ``formula``).
    algorithm : str
        Method used to generate the identifier (e.g. ``rdkit inchi``, ``rdkit smiles``).
    value : str
        The resulting identifier string.
    stationary_points : list[StationaryPointRow]
        Stationary points sharing this identity.
    identity_extras : list[IdentityExtraRow]
        Additional key-value metadata attached to this identity.
    """

    __tablename__ = "identity"
    id: int | None = Field(default=None, primary_key=True)

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )
    identity_extras: list["IdentityExtraRow"] = Relationship(back_populates="identity")


class IdentityExtraRow(BaseRow, table=True):
    """Additional key-value metadata attached to a chemical identity.

    Attributes
    ----------
    identity_id : int
        Foreign key to the parent identity.
    attribute : str
        Name of the extra attribute.
    value : str
        Value of the extra attribute.
    identity : IdentityRow
        The parent identity this extra belongs to.
    """

    __tablename__ = "identity_extras"
    id: int | None = Field(default=None, primary_key=True)

    identity_id: int | None = Field(
        default=None, foreign_key="identity.id", ondelete="CASCADE", nullable=False
    )

    attribute: str
    value: str

    identity: "IdentityRow" = Relationship(back_populates="identity_extras")


class StageRow(BaseRow, table=True):
    """A chemical state (reactant, product, or transition state) in a reaction.

    Attributes
    ----------
    is_ts : bool
        Whether this stage represents a transition state.
    backward_steps : list[StepRow]
        Elementary steps where this stage is the reactant.
    transition_steps : list[StepRow]
        Elementary steps where this stage is the transition state.
    forward_steps : list[StepRow]
        Elementary steps where this stage is the product.
    stationary_points : list[StationaryPointRow]
        Stationary point geometries mapped to this stage.
    """

    __tablename__ = "stage"
    id: int | None = Field(default=None, primary_key=True)

    is_ts: bool = False

    backward_steps: list["StepRow"] = Relationship(
        back_populates="backward_stage",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.backward_stage_id]"},
    )
    transition_steps: list["StepRow"] = Relationship(
        back_populates="transition_stage",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.transition_stage_id]"},
    )
    forward_steps: list["StepRow"] = Relationship(
        back_populates="forward_stage",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.forward_stage_id]"},
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StationaryStageLink
    )


class StepRow(BaseRow, table=True):
    """An elementary reaction step connecting a reactant, transition state, and product.

    Attributes
    ----------
    backward_stage_id : int
        Foreign key to the reactant stage.
    transition_stage_id : int
        Foreign key to the transition state stage.
    forward_stage_id : int, optional
        Foreign key to the product stage.
    is_barrierless : bool
        Whether this step proceeds without a formal transition state.
    backward_stage : StageRow
        The reactant stage for this step.
    transition_stage : StageRow
        The transition state stage for this step.
    forward_stage : StageRow, optional
        The product stage for this step.
    """

    __tablename__ = "step"
    __table_args__ = (
        CheckConstraint(
            "(is_barrierless = TRUE AND transition_stage_id IS NULL) OR "
            "(is_barrierless = FALSE AND transition_stage_id IS NOT NULL)",
            name="check_barrierless_or_transition",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)

    backward_stage_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=False
    )
    transition_stage_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=False
    )
    forward_stage_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=True
    )
    is_barrierless: bool = False

    backward_stage: "StageRow" = Relationship(
        back_populates="backward_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.backward_stage_id]"},
    )
    transition_stage: "StageRow" = Relationship(
        back_populates="transition_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.transition_stage_id]"},
    )
    forward_stage: "StageRow" = Relationship(
        back_populates="forward_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.forward_stage_id]"},
    )
    validations: list["ValidationRow"] = Relationship(
        back_populates="step", link_model=StepValidationLink
    )


@event.listens_for(Session, "before_flush")
def add_inchi_identities(session, flush_context, instances) -> None:  # noqa: ANN001, ARG001
    """Attach InChI and SMILES identities to new stationary point rows before flush."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue
        try:
            inchi_row = IdentityRow.from_geometry(
                geo=obj.geometry,
                algorithm="rdkit inchi",
            )
        except ValueError:
            # NOTE: Add logger
            continue

        existing = session.exec(
            select(IdentityRow).where(
                IdentityRow.algorithm == inchi_row.algorithm,
                IdentityRow.value == inchi_row.value,
            )
        ).first()

        if existing is None:
            smiles = Identity.from_geometry(
                obj.geometry,
                algorithm="rdkit smiles",
            )

            inchi_row.identity_extras.append(
                IdentityExtraRow(
                    attribute="smiles",
                    value=smiles.value,
                )
            )

            session.add(inchi_row)
            existing = inchi_row

        obj.identities.append(existing)


@event.listens_for(GeometryRow, "before_insert")
@event.listens_for(GeometryRow, "before_update")
def ensure_geometry_hash(mapper, connection, target: GeometryRow) -> None:  # noqa: ANN001, ARG001
    """Compute and assign the geometry hash before inserting a GeometryRow."""
    if target.hash is None:
        target.hash = geom.geometry_hash(target)


@event.listens_for(StationaryPointRow, "before_insert")
@event.listens_for(StationaryPointRow, "before_update")
def validate_stationary_order(mapper, connection, target: StationaryPointRow) -> None:  # noqa: ANN001
    """Compute hessian frequencies and verify stationary point order before insert."""
    if target.is_valid and target.hessian_id is None:
        msg = "StationaryPoint cannot be valid without an associated Hessian."
        raise ValueError(msg)

    hess = target.hessian
    if not hess:
        return

    freq, _ = geom.vibrational_analysis(target.geometry, hess.value)
    hess_order = sum(1 for f in freq if f < 0)

    if target.order != hess_order:
        target.is_valid = False

        stmt = insert(mapper.local_table).values(
            geometry_id=target.geometry_id,
            calculation_id=target.calculation_id,
            hessian_id=target.hessian_id,
            order=hess_order,
            is_pseudo=target.is_pseudo,
            is_valid=True,
        )

        connection.execute(stmt)

    else:
        target.is_valid = True
