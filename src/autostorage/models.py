"""SQLModel row definitions for autostorage's schema."""

import uuid
from collections.abc import Sequence
from typing import Any, Self

import numpy as np
import numpy.typing as npt
import pint
import py3Dmol
from autogeom import Geometry, angle, dihedral, distance, ureg
from autogeom.types import CoordinatesField
from sqlalchemy.ext.mutable import MutableDict
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
    AxisKind,
    CompressedArrayTypeDecorator,
    CompressedJSONTypeDecorator,
    IdentityKind,
    Role,
)


def _fk_field(
    target: str,
    *,
    nullable: bool = False,
    index: bool = True,
    primary_key: bool = False,
) -> Any:  # noqa: ANN401
    """Build a foreign-key `Field` to `target` with ON DELETE CASCADE."""
    return Field(
        default=None,
        foreign_key=target,
        ondelete="CASCADE",
        nullable=nullable,
        index=index,
        primary_key=primary_key,
    )


def _link_fk_field(target: str) -> Any:  # noqa: ANN401
    """Build a cascading foreign key that is part of a link table's primary key."""
    # The composite primary key only indexes its leading column; link tables add
    # an explicit index for the other column in `__table_args__`.
    return _fk_field(target, index=False, primary_key=True)


def _role_column() -> Column:
    """Build a column storing a `Role` by value (``"input"``/``"output"``)."""
    return Column(Enum(Role, values_callable=lambda roles: [r.value for r in roles]))


def _json_dict_column() -> Column:
    """Build a JSON column whose dict value tracks in-place changes."""
    return Column(MutableDict.as_mutable(JSON))


# 0. Link rows
# NOTE: Link tables are named by the two entities they connect, in alphabetical order.
class CalculationGeometryLink(SQLModel, table=True):
    """Association table linking geometries to a calculation."""

    __tablename__ = "calculation_geometry_link"
    __table_args__ = (
        Index("ix_calculation_geometry_link_calculation_id", "calculation_id"),
    )

    geometry_id: uuid.UUID | None = _link_fk_field("geometry.id")
    """Foreign key to the linked `GeometryRow`."""
    calculation_id: uuid.UUID | None = _link_fk_field("calculation.id")
    """Foreign key to the linked `CalculationRow`."""
    role: Role = Field(sa_column=_role_column())
    """Role the `GeometryRow` plays for `CalculationRow` (input/output)."""
    geometry: "GeometryRow" = Relationship(back_populates="calculation_links")
    """The linked `GeometryRow`."""
    calculation: "CalculationRow" = Relationship(back_populates="geometry_links")
    """The linked `CalculationRow`."""


class GeometryTrajectoryLink(SQLModel, table=True):
    """Association table linking geometries to a trajectory."""

    __tablename__ = "geometry_trajectory_link"
    __table_args__ = (
        Index("ix_geometry_trajectory_link_trajectory_id", "trajectory_id"),
    )

    geometry_id: uuid.UUID | None = _link_fk_field("geometry.id")
    """Foreign key to the linked `GeometryRow`."""
    trajectory_id: uuid.UUID | None = _link_fk_field("trajectory.id")
    """Foreign key to the linked `TrajectoryRow`."""
    index: list[int] | None = Field(default=None, sa_column=Column(JSON))
    """Position of `geometry` within the `trajectory`."""
    values: list[float | None] | None = Field(default=None, sa_column=Column(JSON))
    """Physical value along each dimension (e.g. a scanned dihedral), aligned with
    `index` and in the units of the matching `TrajectoryAxisRow`.

    On flush, missing values of measurable axes are measured from `geometry`, and
    `pint.Quantity` values are converted to the axis's units.
    """
    geometry: "GeometryRow" = Relationship(back_populates="trajectory_links")
    """The linked `GeometryRow`."""
    trajectory: "TrajectoryRow" = Relationship(back_populates="geometry_links")
    """The linked `TrajectoryRow`."""


class CalculationTrajectoryLink(SQLModel, table=True):
    """Association table linking trajectories to a calculation."""

    __tablename__ = "calculation_trajectory_link"
    __table_args__ = (
        Index("ix_calculation_trajectory_link_calculation_id", "calculation_id"),
    )

    trajectory_id: uuid.UUID | None = _link_fk_field("trajectory.id")
    """Foreign key to the linked `TrajectoryRow`."""
    calculation_id: uuid.UUID | None = _link_fk_field("calculation.id")
    """Foreign key to the linked `CalculationRow`."""
    role: Role = Field(sa_column=_role_column())
    """Role the `TrajectoryRow` plays for `CalculationRow` (input/output)."""
    trajectory: "TrajectoryRow" = Relationship(back_populates="calculation_links")
    """The linked `TrajectoryRow`."""
    calculation: "CalculationRow" = Relationship(back_populates="trajectory_links")
    """The linked `CalculationRow`."""


class StageStationaryLink(SQLModel, table=True):
    """Association table linking stationary points to reaction stages.

    Relationships are managed via `StationaryPointRow.stages` and
    `StageRow.stationaries`, using this table as their `link_model`.
    """

    __tablename__ = "stage_stationary_link"
    __table_args__ = (Index("ix_stage_stationary_link_stage_id", "stage_id"),)

    stationary_id: uuid.UUID | None = _link_fk_field("stationary_point.id")
    """Foreign key to the linked `StationaryPointRow`."""
    stage_id: uuid.UUID | None = _link_fk_field("stage.id")
    """Foreign key to the linked `StageRow`."""


class StepValidationLink(SQLModel, table=True):
    """Association table linking validations to a step.

    Relationships are managed via `ValidationRow.step` and `StepRow.validations`,
    using this table as their `link_model`.
    """

    __tablename__ = "step_validation_link"
    __table_args__ = (Index("ix_step_validation_link_validation_id", "validation_id"),)

    step_id: uuid.UUID | None = _link_fk_field("step.id")
    """Foreign key to the linked `StepRow`."""
    validation_id: uuid.UUID | None = _link_fk_field("validation.id")
    """Foreign key to the linked `ValidationRow`."""


class IdentityStationaryLink(SQLModel, table=True):
    """Association table linking chemical identities to stationary points.

    Removing a link from `StationaryPointRow.identity_links` or
    `IdentityRow.stationary_links` deletes it.
    """

    __tablename__ = "identity_stationary_link"
    __table_args__ = (Index("ix_identity_stationary_link_identity_id", "identity_id"),)

    stationary_id: uuid.UUID | None = _link_fk_field("stationary_point.id")
    """Foreign key to the linked `StationaryPointRow`."""
    identity_id: uuid.UUID | None = _link_fk_field("identity.id")
    """Foreign key to the linked `IdentityRow`."""
    identity_cache: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(MutableDict.as_mutable(CompressedJSONTypeDecorator())),
    )
    """Data that makes generating identities cheaper (e.g. graph isomorphisms).

    Stored as zlib-compressed JSON. Only top-level key changes are tracked in
    place; reassign the dict after editing nested values. Discarded with the
    link when the stationary point's geometry changes.
    """
    stationary: "StationaryPointRow" = Relationship(back_populates="identity_links")
    """The linked `StationaryPointRow`."""
    identity: "IdentityRow" = Relationship(back_populates="stationary_links")
    """The linked `IdentityRow`."""


# 1. Existential data rows
class GeometryRow(SQLModel, Geometry, table=True):
    """Molecular geometry definition and metadata.

    Attributes:
        id: Primary key.
        symbols: Atomic symbols in order.
        coordinates: Atomic coordinates in Angstrom. A `pint.Quantity` with length units
            is converted to Angstrom.
        charge: Total molecular charge.
        spin: Number of unpaired electrons (2S).
        properties: Property values (energies, gradients, Hessians, ...) computed at
            this geometry.
        stationary_points: Stationary points defined by this geometry.
        trajectory_links: Raw link rows connecting this geometry to trajectories.
        calculation_links: Raw link rows connecting this geometry to calculations.
    """

    __tablename__ = "geometry"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: CoordinatesField = Field(
        sa_column=Column(CompressedArrayTypeDecorator())
    )
    charge: int = 0
    spin: int = 0

    properties: list["PropertyValueRow"] = Relationship(
        back_populates="geometry", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="geometry", cascade_delete=True
    )
    trajectory_links: list["GeometryTrajectoryLink"] = Relationship(
        back_populates="geometry", cascade_delete=True
    )
    calculation_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="geometry", cascade_delete=True
    )

    def relabel_atoms(self, indices: Sequence[int]) -> Self:
        """Return a reordered copy of this geometry as a new, unsaved row.

        Unlike `autogeom.Geometry.relabel_atoms`, the copy gets a fresh `id` and
        no relationships, so that it can be added to a session as a new row.
        """
        relabeled = super().relabel_atoms(indices)
        return type(self)(
            **{name: getattr(relabeled, name) for name in Geometry.model_fields}
        )


class TrajectoryAxisRow(SQLModel, table=True):
    """Physical coordinate that one dimension of a trajectory runs along.

    Examples:
        A relaxed scan of the H-O-O-H dihedral of hydrogen peroxide:

        >>> axis = TrajectoryAxisRow(axis=0, kind="dihedral", keys=[0, 1, 2, 3])
        >>> geo = GeometryRow(
        ...     symbols=["H", "O", "O", "H"],
        ...     coordinates=[[0, 0, 1], [0, 0, 0], [0, 1, 0], [1, 1, 0]],
        ... )
        >>> axis.measure(geo)
        90.0
    """

    __tablename__ = "trajectory_axis"

    trajectory_id: uuid.UUID | None = _link_fk_field("trajectory.id")
    """Foreign key to the `TrajectoryRow` this axis describes."""
    axis: int = Field(primary_key=True)
    """Dimension of the trajectory's geometry `index` that this axis describes."""
    kind: AxisKind
    """Kind of coordinate; `OTHER` coordinates are not measured from the geometry."""
    keys: list[int] | None = Field(default=None, sa_column=Column(JSON))
    """Indices of the atoms defining the coordinate (2, 3, or 4 for a distance,
    angle, or dihedral)."""
    units: str | None = None
    """Units of the values along this axis (a `pint` unit string); on flush, defaults
    to Angstrom for distances, degrees for angles, and dimensionless otherwise."""
    label: str | None = None
    """Human-readable description (e.g. ``"H-O-O-H torsion"``)."""
    trajectory: "TrajectoryRow" = Relationship(back_populates="axes")
    """The described `TrajectoryRow`."""

    def measure(self, geo: Geometry) -> float | None:
        """Measure this coordinate in `geo`, in `units`, or `None` for `OTHER` axes."""
        kind = AxisKind(self.kind)
        keys = list(self.keys or [])
        if kind is AxisKind.DISTANCE:
            value = distance(geo, keys)
        elif kind is AxisKind.ANGLE:
            value = angle(geo, keys, degrees=True)
        elif kind is AxisKind.DIHEDRAL:
            value = dihedral(geo, keys, degrees=True)
        else:
            return None
        return self.convert(ureg.Quantity(value, kind.default_units))

    def convert(self, value: object) -> float:
        """Return `value` in `units`; a value without units is assumed to be in them.

        Raises:
            ValueError: If `value` is a `pint.Quantity` with incompatible units.
        """
        if not isinstance(value, pint.Quantity):
            return float(value)  # ty: ignore[invalid-argument-type]
        units = self.units or AxisKind(self.kind).default_units
        try:
            return float(value.m_as(units))
        except pint.DimensionalityError as err:
            msg = f"Expected units compatible with {units!r} but got {value.units:~}."
            raise ValueError(msg) from err


class TrajectoryRow(SQLModel, table=True):
    """Ordered sequence of geometries from a calculation trajectory.

    Attributes:
        id: Primary key.
        ndim: Length of each linked geometry's `index` (inferred from the first link
            if unset).
        axes: Physical coordinates (e.g. a scanned dihedral) that the dimensions run
            along, ordered by `axis`. Dimensions without one are only indexed.
        geometry_links: Raw link rows connecting geometries to this trajectory.
        calculation_links: Raw link rows connecting calculations to this trajectory.
    """

    __tablename__ = "trajectory"

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    ndim: int | None = Field(default=None, nullable=True)

    axes: list["TrajectoryAxisRow"] = Relationship(
        back_populates="trajectory",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "TrajectoryAxisRow.axis"},
    )
    geometry_links: list["GeometryTrajectoryLink"] = Relationship(
        back_populates="trajectory", cascade_delete=True
    )
    calculation_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="trajectory", cascade_delete=True
    )

    def geometries_along(
        self, axis: int = 0, at: Sequence[int] | None = None
    ) -> list[GeometryRow]:
        """Get the geometries along one dimension, ordered by their index along it.

        Args:
            axis: Dimension to run along.
            at: Indices of the other dimensions (in order, skipping `axis`) at which
                to take the slice. Defaults to the lowest index of each.

        Returns:
            The geometries whose index matches `at` in every other dimension.

        Raises:
            ValueError: If the trajectory has no indexed geometries, or `axis` or
                `at` do not fit its number of dimensions.
        """
        return [link.geometry for link in self._links_along(axis, at)]

    def values_along(
        self,
        axis: int = 0,
        at: Sequence[int] | None = None,
        units: str | None = None,
    ) -> npt.NDArray[np.float64]:
        """Get the physical values of `axis` for the geometries of `geometries_along`.

        Args:
            axis: Dimension to run along.
            at: Indices of the other dimensions, as in `geometries_along`.
            units: Units to convert to. Defaults to the axis's units.

        Returns:
            The values along `axis`, with NaN where a geometry has none.

        Raises:
            ValueError: As for `geometries_along`, or if `units` is given for a
                dimension without a `TrajectoryAxisRow`, or is incompatible with it.
        """
        values = np.array(
            [
                np.nan
                if link.values is None or link.values[axis] is None
                else link.values[axis]
                for link in self._links_along(axis, at)
            ],
            dtype=np.float64,
        )
        if units is None:
            return values
        axis_row = next((row for row in self.axes if row.axis == axis), None)
        if axis_row is None:
            msg = f"Trajectory {self.id} has no TrajectoryAxisRow for axis {axis}"
            raise ValueError(msg)
        native = axis_row.units or AxisKind(axis_row.kind).default_units
        try:
            return ureg.Quantity(values, native).m_as(units)
        except pint.DimensionalityError as err:
            msg = f"Cannot convert axis {axis} values from {native!r} to {units!r}."
            raise ValueError(msg) from err

    def _links_along(
        self, axis: int, at: Sequence[int] | None
    ) -> list[GeometryTrajectoryLink]:
        """Get the links of `geometries_along`, ordered by their index along `axis`."""
        links = [link for link in self.geometry_links if link.index is not None]
        if not links:
            msg = f"Trajectory {self.id} has no indexed geometries"
            raise ValueError(msg)

        indices = [list(link.index or []) for link in links]
        ndim = self.ndim if self.ndim is not None else len(indices[0])
        if not 0 <= axis < ndim:
            msg = f"Axis {axis} is out of range for a trajectory with ndim {ndim}"
            raise ValueError(msg)

        others = [dim for dim in range(ndim) if dim != axis]
        if at is None:
            at = [min(idx[dim] for idx in indices) for dim in others]
        if len(at) != len(others):
            msg = f"Expected {len(others)} indices for the other dimensions, got {at}"
            raise ValueError(msg)

        target = list(at)
        matches = [
            (idx[axis], link)
            for idx, link in zip(indices, links, strict=True)
            if [idx[dim] for dim in others] == target
        ]
        return [link for _, link in sorted(matches, key=lambda match: match[0])]

    def view(
        self,
        axis: int = 0,
        at: Sequence[int] | None = None,
        *,
        interval: int = 200,
        view: py3Dmol.view | None = None,
    ) -> py3Dmol.view:
        """Animate the geometries along one dimension with py3Dmol.

        Args:
            axis: Dimension to animate along.
            at: Indices of the other dimensions (in order, skipping `axis`) at which
                to take the slice. Defaults to the lowest index of each.
            interval: Time between frames, in milliseconds.
            view: Existing view to add the animation to. If `None`, create one.

        Returns:
            The view containing the animation.

        Raises:
            ValueError: If no geometries lie along the requested slice.
        """
        geos = self.geometries_along(axis, at)
        if not geos:
            msg = f"No geometries along axis {axis} at {at} in trajectory {self.id}"
            raise ValueError(msg)

        view = py3Dmol.view(width=400, height=400) if view is None else view
        view.addModelsAsFrames("\n".join(geo.xyz_block() for geo in geos), "xyz")
        view.setStyle({"model": -1}, {"stick": {}, "sphere": {"scale": 0.3}})
        view.animate({"loop": "backAndForth", "interval": interval})
        view.zoomTo()
        return view


class ModelRow(SQLModel, table=True):
    """Calculation model specification.

    Attributes:
        id: Primary key.
        program: Quantum chemistry program used (psi4, ORCA, ...)
        program_version: Quantum chemistry program version.
        method: Computational method (B3LYP, MP2, ...)
        basis: Orbital basis set.
        keywords: Additional keywords and options for the calculation.
        calculations: Calculations performed using this model.
    """

    __tablename__ = "model"

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    program: str
    program_version: str | None = None
    method: str
    basis: str | None = None
    keywords: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=_json_dict_column()
    )

    calculations: list["CalculationRow"] = Relationship(
        back_populates="model", cascade_delete=True
    )


class CalculationRow(SQLModel, table=True):
    """Quantum chemistry calculation and its associated data.

    Attributes:
        id: Primary key.
        model_id: Foreign key to the model used for this calculation.
        calc_type: Type of calculation (energy, gradient, hessian, etc.).
        input_provenance: Metadata describing how the input was generated.
        output_provenance: Metadata describing how the output was produced.
        model: Model used for this calculation.
        geometry_links: Raw link rows connecting geometries to this calculation.
        trajectory_links: Raw link rows connecting trajectories to this calculation.
        properties: Property values (energies, gradients, Hessians, ...) produced by
            this calculation.
        validations: Validation results performed by this calculation.
        stationary_points: Stationary points identified by this calculation.
    """

    __tablename__ = "calculation"

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    model_id: uuid.UUID | None = _fk_field("model.id")
    calc_type: str
    input_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=_json_dict_column()
    )
    output_provenance: dict[str, Any] | None = Field(
        default_factory=dict, sa_column=_json_dict_column()
    )

    model: "ModelRow" = Relationship(back_populates="calculations")
    properties: list["PropertyValueRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    validations: list["ValidationRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    geometry_links: list["CalculationGeometryLink"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    trajectory_links: list["CalculationTrajectoryLink"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )


class PropertyKindRow(SQLModel, table=True):
    """A kind of property (e.g. ``energy``, ``gradient``, ``hessian``).

    Rows mirror the in-memory `autostorage.property.PropertyKindRegistry`, keyed
    by name. Validation, unit conversion, and storage dtype are looked up from
    the registry by name, so rows loaded from the database behave the same as
    freshly seeded ones. The units are also stored, so the database records what
    its values mean.
    """

    __tablename__ = "property_kind"

    name: str = Field(primary_key=True)
    """Primary key; name of the registered property kind."""
    units: str
    """Native units (a `pint` unit string) that values of this kind are stored in."""
    property_values: list["PropertyValueRow"] = Relationship(
        back_populates="property_kind"
    )
    """The linked `PropertyValueRow`s."""


class PropertyValueRow(SQLModel, table=True):
    """Property value for a specific geometry and calculation."""

    __tablename__ = "property_value"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    """Primary key."""
    geometry_id: uuid.UUID | None = _fk_field("geometry.id")
    """Foreign key to the linked `GeometryRow`."""
    geometry: "GeometryRow" = Relationship(back_populates="properties")
    """The linked `GeometryRow`."""
    calculation_id: uuid.UUID | None = _fk_field("calculation.id")
    """Foreign key to the linked `CalculationRow`."""
    calculation: "CalculationRow" = Relationship(back_populates="properties")
    """The linked `CalculationRow`."""
    property_kind_name: str | None = _fk_field("property_kind.name")
    """Foreign key to the linked `PropertyKindRow` (e.g. ``"energy"``)."""
    property_kind: "PropertyKindRow" = Relationship(back_populates="property_values")
    """The linked `PropertyKindRow`."""
    value: Any = Field(sa_column=Column(CompressedArrayTypeDecorator(dtype=None)))
    """Value produced by `geometry` and `calculation`, as a NumPy array.

    Stored in the property kind's native units. On flush, a `pint.Quantity` is
    converted to those units, and other values are assumed to be in them already.
    The value is then validated and cast to the kind's dtype (float64, except
    float32 for Hessians), so it may be assigned as a float, sequence, array, or
    quantity.
    """


class ValidationRow(SQLModel, table=True):
    """Validation result for a specific step and calculation.

    Attributes:
        id: Primary key.
        calculation_id: Foreign key to the calculation that performed this validation.
        method: Type of validation step (e.g., ``irc``)
        extras: Additional metadata attached to this validation.
        calculation: Calculation that performed this validation.
        step: Reaction step this validation belongs to.
    """

    __tablename__ = "validation"

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    calculation_id: uuid.UUID | None = _fk_field("calculation.id")

    method: str
    extras: dict[str, Any] = Field(default_factory=dict, sa_column=_json_dict_column())

    calculation: "CalculationRow" = Relationship(back_populates="validations")
    step: "StepRow" = Relationship(
        back_populates="validations", link_model=StepValidationLink
    )


# 2. Stationary point rows
class StationaryPointRow(SQLModel, table=True):
    """A stationary point on a potential energy surface.

    Attributes:
        id: Primary key.
        geometry_id: Foreign key to the underlying molecular geometry.
        calculation_id: Foreign key to the calculation that identified this point.
        order: Hessian index (0 for minima, 1 for first-order saddle points).
        is_pseudo: Whether this point is not a true stationary point (e.g. constrained).
        is_validated: Whether this stationary point has been validated (e.g., by Hessian
            calculation).
        geometry: Geometry defining the coordinates of this point.
        calculation: Calculation that identified this point.
        identity_links: Link rows to this point's chemical identifiers (e.g. InChI,
            SMILES), each with its `identity_cache`.
        stages: Reaction stages this stationary point belongs to.
    """

    __tablename__ = "stationary_point"

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    geometry_id: uuid.UUID | None = _fk_field("geometry.id")
    calculation_id: uuid.UUID | None = _fk_field("calculation.id")
    order: int = 0
    is_pseudo: bool = False
    is_validated: bool = False

    geometry: "GeometryRow" = Relationship(back_populates="stationary_points")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")
    identity_links: list["IdentityStationaryLink"] = Relationship(
        back_populates="stationary", cascade_delete=True
    )
    stages: list["StageRow"] = Relationship(
        back_populates="stationaries", link_model=StageStationaryLink
    )


# 3. Reaction network rows
class StageRow(SQLModel, table=True):
    """A chemical state (reactant, product, or transition state) in a reaction.

    Attributes:
        id: Primary key.
        is_ts: Whether this stage represents a transition state.
        stationaries: Stationary points that make up this stage (bidirectional via
            `link_model=StageStationaryLink`).
        steps: Reaction steps referencing this stage as `stage1`, `stage2`, or
            `stage_ts`. Read-only view derived from `StepRow`'s foreign keys;
            use `stage1`, `stage2`, `stage_ts` relationships on `StepRow` for
            writing.
    """

    __tablename__ = "stage"

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
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
    """An elementary reaction step connecting a reactant, TS, and product."""

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
            text("coalesce(stage_id_ts, '')"),
            unique=True,
        ),
    )

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    """Primary key."""
    # Lookups by `stage_id1` use the unique indexes above (leading column)
    stage_id1: uuid.UUID | None = _fk_field("stage.id", index=False)
    """The step's first non-TS stage (reactant or product)."""
    stage_id2: uuid.UUID | None = _fk_field("stage.id")
    """The step's second non-TS stage (reactant or product)."""
    stage_id_ts: uuid.UUID | None = _fk_field("stage.id", nullable=True)
    """The step's TS stage."""
    is_barrierless: bool = False
    """Whether this step proceeds without a formal TS."""
    validations: list["ValidationRow"] = Relationship(
        back_populates="step", link_model=StepValidationLink
    )
    """Validation calculations performed on `StepRow`."""
    stage1: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id1]"}
    )
    """The step's first non-TS stage (reactant or product)."""
    stage2: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id2]"}
    )
    """The step's second non-TS stage (reactant or product)."""
    stage_ts: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id_ts]"}
    )
    """The step's TS stage, or `None` if barrierless."""


# 4. Identity rows
class IdentityAlgorithmRow(SQLModel, table=True):
    """A chemical identifier algorithm, mirroring an `IdentityAlgorithm`.

    Attributes:
        name: Primary key; the registered algorithm name (e.g. ``rdkit_inchi``).
        kind: Category of identifier produced (e.g. ``stereoisomer``, ``formula``).
        parent_algorithm_name: Foreign key to the parent algorithm, whose identity
            disambiguates this one's `other_geos`, if any.
    """

    __tablename__ = "identity_algorithm"
    model_config = SQLModelConfig(arbitrary_types_allowed=True)

    name: str = Field(primary_key=True)
    kind: IdentityKind
    parent_algorithm_name: str | None = _fk_field(
        "identity_algorithm.name", nullable=True, index=False
    )

    parent_algorithm: "IdentityAlgorithmRow" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[IdentityAlgorithmRow.parent_algorithm_name]",
            "remote_side": "[IdentityAlgorithmRow.name]",
        }
    )
    identities: list["IdentityRow"] = Relationship(back_populates="algorithm")


class IdentityRow(SQLModel, table=True):
    """A chemical identifier associated with one or more stationary points.

    Attributes:
        id: Primary key.
        algorithm_name: Foreign key to the generating `IdentityAlgorithmRow`.
        algorithm: Method used to generate the identifier (e.g. ``rdkit inchi``, ``rdkit
            smiles``); its ``kind`` gives the category (e.g. ``stereoisomer``,
            ``formula``).
        value: The resulting identifier string.
        stationary_links: Link rows to the stationary points sharing this identity.
    """

    __tablename__ = "identity"
    __table_args__ = (
        UniqueConstraint("algorithm_name", "value", name="unique_identity"),
    )

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    algorithm_name: str | None = _fk_field("identity_algorithm.name")
    value: str

    algorithm: "IdentityAlgorithmRow" = Relationship(back_populates="identities")
    stationary_links: list["IdentityStationaryLink"] = Relationship(
        back_populates="identity", cascade_delete=True
    )
