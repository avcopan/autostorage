"""SQLModel row definitions for autostorage's persistence schema."""

import hashlib
import json
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING, Any, Self, dataclass_transform

import numpy as np
from automol import Algorithm, Geometry, Identity, geom
from automol.utils.types import FloatArray
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
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
    func,
    select,
)
from sqlmodel.main import SQLModelConfig
from stereomolgraph.algorithms.symmetry import (
    symmetry_number as _stereo_symmetry_number,
)

from autostorage.exc import MissingPrimaryKeyError

from .types import CalcStatus, CalcType, CompressedArrayTypeDecorator, Role

if TYPE_CHECKING:
    from .database import Database


def _fk_field(target: str, *, nullable: bool = False, index: bool = True) -> Any:  # noqa: ANN401
    """Build a standard foreign-key Field with ON DELETE CASCADE."""
    return Field(
        default=None,
        foreign_key=target,
        ondelete="CASCADE",
        nullable=nullable,
        index=index,
    )


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class TimestampMixin(SQLModel):
    """Mixin adding server-managed creation/update timestamps.

    Annotated as `datetime | None` since the value is unset in Python until the
    database fills it in via `server_default`/`onupdate`; `nullable=False`
    overrides the `NULL`-by-default column that an Optional annotation would
    otherwise produce, since the DB always has a value once the row is flushed.
    """

    created_at: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
    )


@dataclass_transform(kw_only_default=True, field_specifiers=(Field,))
class BaseRow(TimestampMixin, SQLModel):
    """Base for models with a primary ID."""

    id: int | None = Field(default=None, primary_key=True)


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
        prov: dict[str, Any] | None = None,
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

    @classmethod
    def create(cls, *rows: BaseRow, **attrs: object) -> Self:
        """Construct a link, matching each row to its relationship by type.

        Parameters
        ----------
        *rows
            The rows to link (e.g. a ``GeometryRow`` and a ``CalculationRow``),
            in any order.
        **attrs
            Extra attributes to set on the link (e.g. ``role``).

        Returns
        -------
        Self
            The constructed (unsaved) link row.
        """
        relationships = sa_inspect(cls, raiseerr=True).relationships
        fields: dict[str, BaseRow] = {}
        for row in rows:
            matches = [
                rel.key
                for rel in relationships
                if rel.key not in fields and isinstance(row, rel.mapper.class_)
            ]
            if not matches:
                msg = f"{cls.__name__} has no unmatched relationship for {row!r}."
                raise ValueError(msg)
            if len(matches) > 1:
                # Ambiguous: two+ unfilled relationships share this row's type,
                # so matching by type alone can't tell them apart (e.g. a link
                # table with two relationships to the same row model). Raise
                # rather than silently picking one by declaration order.
                msg = (
                    f"{cls.__name__} has multiple unmatched relationships "
                    f"{matches} for {row!r}; construct this link directly instead."
                )
                raise ValueError(msg)
            fields[matches[0]] = row
        return cls(**fields, **attrs)


def _geometry_hash(
    symbols: list[str], coordinates: FloatArray, charge: int, spin: int
) -> str:
    """Compute a hash identifying bit-identical geometry content."""
    hasher = hashlib.sha256()
    hasher.update(json.dumps(symbols).encode())
    hasher.update(np.asarray(coordinates, dtype=np.float64).tobytes())
    hasher.update(charge.to_bytes(8, "big", signed=True))
    hasher.update(spin.to_bytes(8, "big", signed=True))
    return hasher.hexdigest()


# Geometry table
class GeometryRow(BaseRow, Geometry, table=True):
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
    geometry_hash
        Content hash of `symbols`/`coordinates`/`charge`/`spin`, used to reject
        exactly-duplicate geometries (see `find_or_create`).
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
    __table_args__ = (UniqueConstraint("geometry_hash", name="unique_geometry_hash"),)

    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(CompressedArrayTypeDecorator()))
    charge: int
    spin: int
    geometry_hash: str | None = Field(default=None, nullable=False)

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

    @cached_property
    def symmetry_number(self) -> int:
        """Symmetry number from stereo-preserving graph automorphisms.

        Cached per instance since counting graph isomorphisms is expensive.
        """
        graph = geom.stereo_mol_graph(self)
        return _stereo_symmetry_number(graph)

    @classmethod
    def find_or_create(  # noqa: PLR0913
        cls,
        db: "Database",
        *,
        symbols: list[str],
        coordinates: FloatArray,
        charge: int,
        spin: int,
        commit: bool = True,
    ) -> Self:
        """Return the matching geometry row, creating and saving one if absent.

        Matches on exact content via `geometry_hash`, so this only reuses
        bit-identical geometries.

        Parameters
        ----------
        commit, optional
            If True (default), commit a newly-created row immediately. If
            False, only flush it (still assigns `.id`), leaving the caller's
            transaction open — for a caller staging several dedup lookups
            that must succeed or fail together.
        """
        geometry_hash = _geometry_hash(symbols, coordinates, charge, spin)
        stmt = select(cls).where(cls.geometry_hash == geometry_hash)
        existing = db.exec_first(stmt)
        if existing is not None:
            return existing

        row = cls(symbols=symbols, coordinates=coordinates, charge=charge, spin=spin)
        db.add(row)
        if commit:
            db.commit()
        else:
            db.flush()
        return row


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

    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
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
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
    value: FloatArray = Field(sa_column=Column(CompressedArrayTypeDecorator()))

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
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")

    value: np.ndarray = Field(
        sa_column=Column(CompressedArrayTypeDecorator(dtype=np.float32))
    )

    calculation: "CalculationRow" = Relationship()
    geometry: "GeometryRow" = Relationship(back_populates="hessians")

    @cached_property
    def harmonic_frequencies(self) -> tuple[float, ...]:
        """Harmonic frequencies derived from the Hessian.

        Cached per instance, since vibrational analysis re-diagonalizes the
        Hessian on every call and `.order` (used by `_recompute_geometry_
        stationary_validity` for every sibling Hessian of a geometry, on
        every relevant flush) depends on it. Invalidated on `value` update
        by `invalidate_hessian_frequency_cache` in `events.py`.
        """
        freqs, _ = geom.vibrational_analysis(geo=self.geometry, hess=self.value)
        return freqs

    @property
    def order(self) -> int:
        """Hessian order."""
        return sum(1 for f in self.harmonic_frequencies if f < 0.0)


# Trajectory table
class TrajectoryRow(BaseRow, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes
    ----------
    geometry_links
        Raw link rows connecting geometries to this trajectory.
    calculation_links
        Raw link rows connecting calculations to this trajectory.
    """

    __tablename__ = "trajectory"

    geometry_links: list["TrajectoryGeometryLink"] = Relationship(
        back_populates="trajectory"
    )
    calculation_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="trajectory"
    )


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
    __table_args__ = (
        Index("ix_trajectory_geometry_link_trajectory_id", "trajectory_id"),
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


# Link tables declared here, ahead of the StationaryPointRow/IdentityRow and
# StationaryPointRow/StageRow entities they connect, because SQLModel's
# `link_model=` kwarg needs the actual class object at class-body-evaluation
# time — unlike every other cross-model reference in this file, it can't be
# satisfied by a lazily-resolved string forward ref.
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
    __table_args__ = (Index("ix_stationary_identity_link_identity_id", "identity_id"),)

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
    __table_args__ = (Index("ix_stationary_stage_link_stage_id", "stage_id"),)

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
    is_valid
        Whether `order` agrees with the consensus order of its geometry's
        Hessians (see `autostorage.events.revalidate_geometry_orders_on_insert_update`).
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

    geometry_id: int | None = _fk_field("geometry.id")
    calculation_id: int | None = _fk_field("calculation.id")
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

    def identity(
        self,
        *,
        kind: str | None = None,
        algorithm: Any | None = None,  # noqa: ANN401
    ) -> "IdentityRow | None":
        """Return the first loaded identity matching kind and/or algorithm.

        Searches `self.identities` (the already-loaded relationship list),
        not the database — use `StationaryPointRow.query` for a DB lookup.
        """
        return next(
            (
                i
                for i in self.identities
                if (kind is None or i.kind == kind)
                and (algorithm is None or i.algorithm == algorithm)
            ),
            None,
        )


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
    __table_args__ = (
        UniqueConstraint("kind", "algorithm", "value", name="unique_identity"),
    )

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )
    identity_extras: list["IdentityExtraRow"] = Relationship(back_populates="identity")

    @classmethod
    def find_or_create(
        cls,
        db: "Database",
        *,
        algorithm: Algorithm,
        value: str,
        commit: bool = True,
    ) -> Self:
        """Return the matching identity row, creating and saving one if absent.

        `kind` isn't a parameter here since it's fully determined by
        `algorithm` (see `Identity.from_value`), so matching on
        `(algorithm, value)` is equivalent to `unique_identity`'s full
        `(kind, algorithm, value)` constraint.

        Parameters
        ----------
        commit, optional
            If True (default), commit a newly-created row immediately. If
            False, only flush it (still assigns `.id`), leaving the caller's
            transaction open — for a caller staging several dedup lookups
            that must succeed or fail together.
        """
        stmt = select(cls).where(cls.algorithm == algorithm, cls.value == value)
        existing = db.exec_first(stmt)
        if existing is not None:
            return existing

        row = cls.from_value(value, algorithm=algorithm)
        db.add(row)
        if commit:
            db.commit()
        else:
            db.flush()
        return row


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
        default=None,
        foreign_key="identity.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
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
    stationaries
        Stationary points that make up this stage.
    steps
        Reaction steps referencing this stage as `stage1`, `stage2`, or
        `stage_ts` (read-only; derived from `StepRow`'s foreign keys).
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

    @classmethod
    def find_or_create(
        cls,
        db: "Database",
        stationaries: list["StationaryPointRow"],
        *,
        is_ts: bool = False,
    ) -> Self:
        """Return the matching stage row, creating and saving one if absent.

        Note
        ----
        Unlike `ModelRow`/`StepRow`, there is no DB-level uniqueness
        constraint backing this dedup, so it relies entirely on
        `StageRow.query`'s app-level lookup.
        """
        existing = cls.query(db, stationaries, is_ts=is_ts)
        if existing is not None:
            return existing

        row = cls(stationaries=stationaries, is_ts=is_ts)
        db.add(row)
        db.commit()
        return row


# Declared here, ahead of StepRow, for the same `link_model=` reason as
# StationaryIdentityLink/StationaryStageLink above.
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


class StepRow(BaseRow, table=True):
    """An elementary reaction step connecting a reactant, transition state, and product.

    Attributes
    ----------
    stage_id1, stage_id2
        Foreign keys to the step's two non-TS stages (stored with
        `stage_id1 < stage_id2`).
    stage_id_ts
        Foreign key to the step's transition-state stage, or `None` for a
        barrierless step.
    is_barrierless
        Whether this step proceeds without a formal transition state.
    stage1, stage2
        The step's two non-TS stages.
    stage_ts
        The step's transition-state stage, or `None` if barrierless.
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
        # constraint. This expression index closes that gap at the DB level,
        # defense-in-depth alongside `StepRow.query`'s app-level lookup.
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

    @classmethod
    def find_or_create(
        cls,
        db: "Database",
        stage1: "StageRow",
        stage2: "StageRow",
        stage_ts: "StageRow | None" = None,
    ) -> Self:
        """Return the matching step row, creating and saving one if absent."""
        existing = cls.query(db, stage1, stage2, stage_ts)
        if existing is not None:
            return existing

        row = cls(stage1=stage1, stage2=stage2, stage_ts=stage_ts)
        db.add(row)
        db.commit()
        return row


# Calculation rows
class ModelRow(BaseRow, table=True):
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
    __table_args__ = (
        UniqueConstraint(
            "program",
            "program_version",
            "method",
            "basis",
            name="unique_model",
        ),
        # `unique_model` doesn't catch duplicates when `program_version` or `basis`
        # is NULL (see `find_or_create` below). This expression index closes that
        # gap at the DB level, defense-in-depth alongside the app-level lookup.
        Index(
            "unique_model_null_safe",
            "program",
            text("coalesce(program_version, '')"),
            "method",
            text("coalesce(basis, '')"),
            unique=True,
        ),
    )

    program: str
    program_version: str | None = None
    method: str
    basis: str | None = None

    @classmethod
    def find_or_create(  # noqa: PLR0913
        cls,
        db: "Database",
        *,
        program: str,
        method: str,
        program_version: str | None = None,
        basis: str | None = None,
        commit: bool = True,
    ) -> Self:
        """Return the matching model row, creating and saving one if absent.

        ``unique_model`` doesn't catch duplicates when ``program_version``
        or ``basis`` is NULL, since SQL treats NULL as distinct from itself
        in unique constraints. Callers that don't always supply both should
        use this instead of constructing and adding a ``ModelRow`` directly,
        to avoid silently accumulating duplicate rows for the same model.

        Parameters
        ----------
        commit, optional
            If True (default), commit a newly-created row immediately. If
            False, only flush it (still assigns `.id`), leaving the caller's
            transaction open — for a caller staging several dedup lookups
            that must succeed or fail together.
        """
        stmt = select(cls).where(
            cls.program == program,
            cls.program_version == program_version,
            cls.method == method,
            cls.basis == basis,
        )
        existing = db.exec_first(stmt)
        if existing is not None:
            return existing

        row = cls(
            program=program,
            program_version=program_version,
            method=method,
            basis=basis,
        )
        db.add(row)
        if commit:
            db.commit()
        else:
            db.flush()
        return row


class CalculationRow(BaseRow, table=True):
    """Quantum chemistry calculation and its associated data.

    Attributes
    ----------
    model_id
        Foreign key to the model used for this calculation.
    calc_type
        Type of calculation performed.
    status
        Lifecycle status of this calculation.
    error_message
        Error message recorded for a failed calculation, if any.
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
    """

    __tablename__ = "calculation"

    model_id: int | None = Field(
        default=None,
        foreign_key="model.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )
    calc_type: CalcType = Field(
        sa_column=Column(Enum(CalcType, values_callable=lambda x: [e.value for e in x]))
    )
    status: CalcStatus = Field(
        default=CalcStatus.PENDING,
        sa_column=Column(
            Enum(CalcStatus, values_callable=lambda x: [e.value for e in x])
        ),
    )
    error_message: str | None = Field(default=None)
    # Intentionally unbounded free-form JSON; add a size/schema guardrail if
    # these are ever populated from a less-trusted input path.
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

    @property
    def input_geometries(self) -> list["GeometryRow"]:
        """Geometries linked to this calculation with an INPUT role."""
        return [
            link.geometry for link in self.geometry_links if link.role == Role.INPUT
        ]

    @property
    def output_geometries(self) -> list["GeometryRow"]:
        """Geometries linked to this calculation with an OUTPUT role."""
        return [
            link.geometry for link in self.geometry_links if link.role == Role.OUTPUT
        ]

    @property
    def input_trajectories(self) -> list["TrajectoryRow"]:
        """Trajectories linked to this calculation with an INPUT role."""
        return [
            link.trajectory for link in self.trajectory_links if link.role == Role.INPUT
        ]

    @property
    def output_trajectories(self) -> list["TrajectoryRow"]:
        """Trajectories linked to this calculation with an OUTPUT role."""
        return [
            link.trajectory
            for link in self.trajectory_links
            if link.role == Role.OUTPUT
        ]


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
    step
        Reaction step this validation belongs to.
    """

    __tablename__ = "validation"

    calculation_id: int | None = _fk_field("calculation.id")

    method: str
    # Intentionally unbounded free-form JSON; add a size/schema guardrail if
    # this is ever populated from a less-trusted input path.
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    calculation: "CalculationRow" = Relationship()
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )
