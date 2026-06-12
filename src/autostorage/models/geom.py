"""Geometry models."""

from typing import TYPE_CHECKING

from automatics import Geometry, Identity, geom
from automatics.utils.types import FloatArray
from sqlalchemy import event
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship, Session, select

from ..utils.types import FloatArrayTypeDecorator
from .base import BaseRow

if TYPE_CHECKING:
    from .calculation import CalculationRow, EnergyRow


class TrajectoryGeometryLink(BaseRow, table=True):
    """Link Geometries produced by a trajectory."""

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
    """
    Link StationaryPointRow to IdentityRow.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    identity_id
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
    """
    Link StationaryPointRows to StageRows.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    stage_id
        Foreign key to the linked reaction stage.
    """

    __tablename__ = "stationary_stage_link"

    stationary_id: int = Field(
        foreign_key="stationary_point.id", primary_key=True, ondelete="CASCADE"
    )
    stage_id: int = Field(foreign_key="stage.id", primary_key=True, ondelete="CASCADE")


class GeometryRow(BaseRow, Geometry, table=True):
    """
    Molecular geometry definition and metadata.

    Attributes
    ----------
    symbols
        List of atomic symbols in order.
    coordinates
        Atomic coordinates in Angstrom.
    charge
        Total molecular charge.
    spin
        Number of unpaired electrons (2S).
    hash
        Unique hash of the geometry for indexing.
    calculations
        List of Calculations using GeometryRow instance as an input.
    energies
        List of calculated energies for this geometry.
    stationary_points
        StationaryPointRow associated with this geometry.
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

    def xyz_block(self) -> str:
        """Write the GeometryRow to a formatted xyz block."""
        return geom.xyz_block(self)


class TrajectoryRow(BaseRow, table=True):
    """
    Trajectory primary container.

    Attributes
    ----------
    id
        Primary key.
    [SQL] calculation
        Parent calculation.
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
        cls, geos: list["GeometryRow"], indices: list[int | list[int]] | None = None
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
    """
    Definition of a stationary point on a potential energy surface.

    Attributes
    ----------
    geometry_id
        Foreign key to the underlying molecular geometry.
    calculation_id
        Foreign key to the calculation identifying this point.
    order
        Hessian index (0 for minima, 1 for saddle points).
    is_pseudo
        Flag for points that are not true stationary points (e.g., constrained).
    [SQL] geometry
        GeometryRow defining the point's coordinates.
    [SQL] calculation
        Parent CalculationRow.
    [SQL] identities
        List of chemical identifiers (InChI, etc.).
    [SQL] metrics
        Comparison metrics (conformer analysis).
    [SQL] stages
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

    order: int = 0
    is_pseudo: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")
    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryIdentityLink
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryStageLink
    )


class IdentityRow(BaseRow, Identity, table=True):
    """
    Chemical identifiers for stationary points.

    Attributes
    ----------
    kind
        Category of identity (e.g., 'stereoisomer', 'formula').
    algorithm
        The method used (e.g., 'InChI', 'SMILES').
    value
        The resulting string identifier.
    [SQL] stationary_points
        Stationary points sharing this identity.
    """

    __tablename__ = "identity"
    id: int | None = Field(default=None, primary_key=True)

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )
    identity_extras: list["IdentityExtraRow"] = Relationship(back_populates="identity")


class IdentityExtraRow(BaseRow, table=True):
    """
    Extra values to attach to stationary point identity entry.

    Attributes
    ----------
    identity_id
        Foreign key to the parent identity.
    attribute
        Label of extra.
    value
        Value of extra.
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
    """
    A specific chemical state (reactant, product, or TS) in a reaction.

    Attributes
    ----------
    is_ts
        Whether this stage represents a transition state.
    [SQL] steps_1, steps_2
        Connection to StepRows where this stage is a reactant or product.
    [SQL] steps_ts
        Connection to StepRows where this stage is the transition state.
    [SQL] stationary_points
        Geometries mapped to this reaction stage.
    """

    __tablename__ = "stage"
    id: int | None = Field(default=None, primary_key=True)

    is_ts: bool = Field(description="Stage represents transition state.")

    reactant_steps: list["StepRow"] = Relationship(
        back_populates="reactant_stage",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.reactant_stage_id]"},
    )
    transition_steps: list["StepRow"] = Relationship(
        back_populates="transition_stage",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.transition_stage_id]"},
    )
    product_steps: list["StepRow"] = Relationship(
        back_populates="product_stage",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.product_stage_id]"},
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StationaryStageLink
    )


class StepRow(BaseRow, table=True):
    """
    An elementary reaction step connecting multiple stages.

    Attributes
    ----------
    stage_id1
        Foreign key to the first reactant/product stage.
    stage_id2
        Foreign key to the second reactant/product stage.
    stage_id_ts
        Foreign key to the transition state stage.
    is_barrierless
        Flag for reactions without a formal transition state.
    [SQL] stage1, stage2, stage_ts
        The specific StageRows linked by this step.
    """

    __tablename__ = "step"
    id: int | None = Field(default=None, primary_key=True)

    reactant_stage_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=False
    )
    transition_stage_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=False
    )
    product_stage_id: int | None = Field(
        default=None, foreign_key="stage.id", index=True, nullable=True
    )
    is_barrierless: bool

    reactant_stage: "StageRow" = Relationship(
        back_populates="reactant_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.reactant_stage_id]"},
    )
    transition_stage: "StageRow" = Relationship(
        back_populates="transition_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.transition_stage_id]"},
    )
    product_stage: "StageRow" = Relationship(
        back_populates="product_steps",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.product_stage_id]"},
    )


@event.listens_for(Session, "before_flush")
def add_inchi_identities(session, flush_context, instances) -> None:  # noqa: ANN001, ARG001
    """Add InChI and SMILES to new stationary point rows."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        inchi_row = IdentityRow.from_geometry(
            geo=obj.geometry,
            algorithm="rdkit inchi",
        )

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
def on_geometry_insert(mapper, connection, target: GeometryRow) -> None:  # noqa: ANN001, ARG001
    """Auto-tag InChI identity after inserting a StationaryPoint."""
    if target.hash is None:
        target.hash = geom.geometry_hash(target)
