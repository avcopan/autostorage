"""SQLAlchemy ORM event listeners for validation and auto-managed identities.

The session-level listeners in this module are registered on `AutostorageSession`
(returned by `Database.session()`), so they do not affect unrelated SQLAlchemy
sessions in the same process.
"""

import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field

import pint
from autogeom import GeometryConversionError, ureg
from sqlalchemy import event, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, UOWTransaction, aliased
from sqlmodel import Session, col, select

from .identity import IdentityAlgorithm, IdentityAlgorithmRegistry
from .models import (
    GeometryRow,
    GeometryTrajectoryLink,
    IdentityAlgorithmRow,
    IdentityRow,
    IdentityStationaryLink,
    PropertyKindRow,
    PropertyValueRow,
    StationaryPointRow,
    StepRow,
    TrajectoryAxisRow,
    TrajectoryRow,
)
from .property import PropertyKindRegistry, hessian_property_kind
from .types import AxisKind


class AutostorageSession(Session):
    """`sqlmodel.Session` with autostorage's validation and identity listeners."""


class IdentityGenerationWarning(UserWarning):
    """An identity algorithm could not generate an identity for a geometry."""


# Errors that the built-in identity functions raise for unsupported or unperceivable
# geometries (e.g. metals, no valid Lewis structure, failed InChI generation).
_IDENTITY_ERRORS = (GeometryConversionError, NotImplementedError, ValueError)


def _ordered_algorithms() -> Iterator[IdentityAlgorithm]:
    """Yield registered algorithms (and their parents) with parents first."""
    seen: set[str] = set()

    def _visit(alg: IdentityAlgorithm) -> Iterator[IdentityAlgorithm]:
        if alg.name in seen:
            return
        if alg.parent is not None:
            yield from _visit(alg.parent)
        seen.add(alg.name)
        yield alg

    for alg in IdentityAlgorithmRegistry.algorithms:
        yield from _visit(alg)


def create_identity_algorithms(session: Session) -> None:
    """Create or update a row for every registered identity algorithm."""
    for alg in _ordered_algorithms():
        parent_name = alg.parent.name if alg.parent is not None else None
        row = session.get(IdentityAlgorithmRow, alg.name)
        if row is None:
            row = IdentityAlgorithmRow(name=alg.name, kind=alg.kind)
            session.add(row)
        row.kind = alg.kind
        row.parent_algorithm_name = parent_name
    session.commit()


def create_property_kinds(session: Session) -> None:
    """Create a row for every registered property kind that is missing one.

    Raises:
        ValueError: If a stored kind's units differ from the registered ones, since
            its stored values would then be misread.
    """
    for prop_kind in PropertyKindRegistry.property_kinds:
        row = session.get(PropertyKindRow, prop_kind.name)
        if row is None:
            session.add(PropertyKindRow(name=prop_kind.name, units=prop_kind.units))
        elif row.units != prop_kind.units:
            msg = (
                f"Property kind {prop_kind.name!r} is stored in {row.units!r}, but "
                f"registered with units {prop_kind.units!r}."
            )
            raise ValueError(msg)
    session.commit()


@event.listens_for(StepRow, "before_insert")
@event.listens_for(StepRow, "before_update")
def sort_step_stage_ids(
    mapper: Mapper[StepRow],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: StepRow,
) -> None:
    """Auto-sort stage_id1 and stage_id2 so stage_id1 < stage_id2."""
    if (
        target.stage_id1 is not None
        and target.stage_id2 is not None
        and target.stage_id1 > target.stage_id2
    ):
        target.stage_id1, target.stage_id2 = target.stage_id2, target.stage_id1


@event.listens_for(StepRow, "before_insert")
@event.listens_for(StepRow, "before_update")
def verify_step_barrierless_consistency(
    mapper: Mapper[StepRow],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: StepRow,
) -> None:
    """Verify that `is_barrierless` is True exactly when `stage_id_ts` is None."""
    has_ts = target.stage_id_ts is not None
    if target.is_barrierless == has_ts:
        msg = (
            "Step with transition state (stage_id_ts!=None) must have "
            "is_barrierless=False"
            if has_ts
            else "Barrierless step (stage_id_ts=None) must have is_barrierless=True"
        )
        raise ValueError(msg)


def _pending[T](session: Session, cls: type[T]) -> list[T]:
    """Return new and modified objects of type `cls` in `session`.

    A list (rather than a generator) is returned, so that callers may modify the
    session while iterating.
    """
    return [obj for obj in (*session.new, *session.dirty) if isinstance(obj, cls)]


def _property_kind_name(obj: PropertyValueRow) -> str | None:
    """Return the property kind name of `obj`, preferring the relationship.

    The `property_kind_name` foreign key is only synchronized from the
    `property_kind` relationship during the flush itself, after "before_flush".
    """
    if obj.property_kind is not None:
        return obj.property_kind.name
    return obj.property_kind_name


def _resolve_geometry(
    session: Session, obj: PropertyValueRow | StationaryPointRow
) -> GeometryRow | None:
    """Return the geometry of `obj`, via its relationship or foreign key."""
    if obj.geometry is not None:
        return obj.geometry
    if obj.geometry_id is not None:
        return session.get(GeometryRow, obj.geometry_id)
    return None


@event.listens_for(AutostorageSession, "before_flush")
def verify_property_values_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Convert property values to their kind's native units and dtype, and validate.

    A `pint.Quantity` is converted to the kind's units; other values are assumed
    to be in those units already.
    """
    for obj in _pending(session, PropertyValueRow):
        name = _property_kind_name(obj)
        geo_row = _resolve_geometry(session, obj)
        if name is None or geo_row is None:
            # Missing foreign keys are rejected by the database
            continue

        prop_kind = PropertyKindRegistry.get(name)
        where = (
            f"Property {name!r} for GeometryRow {geo_row.id} and "
            f"CalculationRow {obj.calculation_id}"
        )
        try:
            value = prop_kind.to_native(obj.value)
        except ValueError as err:
            msg = f"{where}: {err}"
            raise ValueError(msg) from err
        if not prop_kind.validation_fn(value, geo_row):
            msg = f"{where} does not match the expected shape."
            raise ValueError(msg)
        obj.value = value


def _has_hessian(session: Session, geo_row: GeometryRow) -> bool:
    """Return whether a Hessian is stored, or pending, for `geo_row`."""
    hessian = hessian_property_kind.name
    if any(_property_kind_name(p) == hessian for p in geo_row.properties):
        return True
    return any(
        isinstance(obj, PropertyValueRow)
        and (obj.geometry is geo_row or obj.geometry_id == geo_row.id)
        and _property_kind_name(obj) == hessian
        for obj in session.new
    )


@event.listens_for(AutostorageSession, "before_flush")
def verify_valid_stationary_has_hessian(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Verify that stationary points marked as validated have a Hessian."""
    for obj in _pending(session, StationaryPointRow):
        if not obj.is_validated:
            continue

        geo_row = _resolve_geometry(session, obj)
        if geo_row is not None and not _has_hessian(session, geo_row):
            msg = (
                "StationaryPointRow cannot be marked as validated without a "
                f"Hessian attached to its geometry (geometry_id={geo_row.id})"
            )
            raise ValueError(msg)


@event.listens_for(AutostorageSession, "before_flush")
def verify_trajectory_geometry_ndim(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Ensure each linked geometry's index length matches its trajectory's ndim.

    A trajectory without an ndim adopts the index length of its first link.
    This runs before the flush (rather than in a mapper-level "before_insert"
    hook) so that the inferred `TrajectoryRow.ndim` is persisted too.
    """
    for link in _pending(session, GeometryTrajectoryLink):
        traj = _resolve_trajectory(session, link)
        if traj is None:
            continue

        index_len = None if link.index is None else len(link.index)
        if index_len is None:
            if traj.ndim is not None:
                msg = f"Geometry index is missing but trajectory ndim is {traj.ndim}"
                raise ValueError(msg)
        elif traj.ndim is None:
            traj.ndim = index_len
        elif index_len != traj.ndim:
            msg = (
                f"Geometry index length {index_len} does not match "
                f"trajectory ndim {traj.ndim}"
            )
            raise ValueError(msg)


def _resolve_trajectory(
    session: Session, link: GeometryTrajectoryLink | TrajectoryAxisRow
) -> TrajectoryRow | None:
    """Return the trajectory of `link`, via its relationship or foreign key."""
    if link.trajectory is not None:
        return link.trajectory
    if link.trajectory_id is not None:
        return session.get(TrajectoryRow, link.trajectory_id)
    return None


def _check_axis(axis: TrajectoryAxisRow, traj: TrajectoryRow | None) -> None:
    """Validate `axis` against its kind and trajectory, and default its units.

    Raises:
        ValueError: If the kind, keys, units, or axis number are invalid.
    """
    try:
        kind = AxisKind(axis.kind)
    except ValueError as err:
        msg = f"Unknown axis kind {axis.kind!r}; expected one of {list(AxisKind)}"
        raise ValueError(msg) from err
    count = kind.key_count
    if count is not None and len(axis.keys or []) != count:
        msg = f"A {kind} axis needs {count} atom keys, got {axis.keys}"
        raise ValueError(msg)
    if axis.units is None:
        axis.units = kind.default_units
    try:
        unit = ureg.Unit(axis.units)
    except (pint.UndefinedUnitError, AttributeError, TypeError, ValueError) as err:
        msg = f"Invalid units {axis.units!r} for axis {axis.axis}: {err}"
        raise ValueError(msg) from err
    if count is not None and not unit.is_compatible_with(kind.default_units):
        msg = f"Units {axis.units!r} are not valid for a {kind} axis"
        raise ValueError(msg)
    if traj is not None and traj.ndim is not None and not 0 <= axis.axis < traj.ndim:
        msg = f"Axis {axis.axis} is out of range for a trajectory with ndim {traj.ndim}"
        raise ValueError(msg)


def _fill_link_values(
    session: Session,
    link: GeometryTrajectoryLink,
    traj: TrajectoryRow,
    axes: dict[int, TrajectoryAxisRow],
) -> None:
    """Convert the given values of `link`, and measure the missing ones.

    Raises:
        ValueError: If the values don't match the trajectory's ndim, or a quantity
            has incompatible units or belongs to a dimension without an axis.
    """
    if link.values is None and not axes:
        return
    if traj.ndim is None:
        msg = "Geometry values require an index (trajectory ndim is unset)"
        raise ValueError(msg)
    values = [None] * traj.ndim if link.values is None else list(link.values)
    if len(values) != traj.ndim:
        msg = (
            f"Geometry values length {len(values)} does not match "
            f"trajectory ndim {traj.ndim}"
        )
        raise ValueError(msg)

    geo_row = link.geometry
    if geo_row is None and link.geometry_id is not None:
        geo_row = session.get(GeometryRow, link.geometry_id)
    for dim, value in enumerate(values):
        axis = axes.get(dim)
        if value is None:
            if axis is not None and geo_row is not None:
                values[dim] = axis.measure(geo_row)
        elif axis is not None:
            values[dim] = axis.convert(value)
        elif isinstance(value, pint.Quantity):
            msg = f"Value {value:~} has units, but axis {dim} has no TrajectoryAxisRow"
            raise ValueError(msg)
        else:
            values[dim] = float(value)
    link.values = values


@event.listens_for(AutostorageSession, "before_flush")
def fill_trajectory_axis_values(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Validate trajectory axes, and fill in the values of their geometries.

    Missing values of measurable axes (distances, angles, dihedrals) are measured
    from each geometry, and `pint.Quantity` values are converted to the axis's
    units. Adding an axis to a trajectory fills in the values of its existing
    geometries. Registered after `verify_trajectory_geometry_ndim`, so that the
    inferred ndim is available.
    """
    # Rows aren't hashable, so they are keyed by `id()`
    axes_by_traj: dict[int, dict[int, TrajectoryAxisRow]] = {}

    def _axes(traj: TrajectoryRow) -> dict[int, TrajectoryAxisRow]:
        key = id(traj)
        if key not in axes_by_traj:
            axes_by_traj[key] = {axis.axis: axis for axis in traj.axes}
        return axes_by_traj[key]

    links = {id(link): link for link in _pending(session, GeometryTrajectoryLink)}
    for axis in _pending(session, TrajectoryAxisRow):
        traj = _resolve_trajectory(session, axis)
        _check_axis(axis, traj)
        if traj is not None:
            # Include axes linked only by foreign key
            _axes(traj)[axis.axis] = axis
            links.update((id(link), link) for link in traj.geometry_links)

    for link in links.values():
        traj = _resolve_trajectory(session, link)
        if traj is not None:
            _fill_link_values(session, link, traj, _axes(traj))


type _IdentityKey = tuple[str, str]
"""An identity's `(algorithm_name, value)`, unique among `IdentityRow`s."""


@dataclass
class _IdentityFlushContext:
    """Per-flush state shared by the identity-resolution helpers below.

    Autoflush is suppressed while "before_flush" handlers run, so identities
    created earlier in the same flush are not visible to queries. They are
    cached here, keyed by algorithm name and value, so that repeated lookups
    reuse the pending row instead of creating a duplicate that would collide with
    the `(algorithm_name, value)` unique constraint.
    """

    session: Session
    algorithms: list[IdentityAlgorithm] = field(
        default_factory=lambda: list(_ordered_algorithms())
    )
    cache: dict[_IdentityKey, IdentityRow] = field(default_factory=dict)
    # Geometries of stationary points added in this flush, keyed by
    # (parent identity key, algorithm name) and then by their identity value
    pending_siblings: dict[tuple[_IdentityKey, str], dict[str, GeometryRow]] = field(
        default_factory=dict
    )


def _get_or_create_identity(
    ctx: _IdentityFlushContext, algorithm_name: str, value: str
) -> IdentityRow:
    """Look up a pending or persisted identity, creating one if none exists."""
    key = (algorithm_name, value)
    ident = ctx.cache.get(key)
    if ident is None:
        ident = ctx.session.exec(
            select(IdentityRow).where(
                col(IdentityRow.algorithm_name) == algorithm_name,
                col(IdentityRow.value) == value,
            )
        ).one_or_none()
    if ident is None:
        ident = IdentityRow(algorithm_name=algorithm_name, value=value)
        ctx.session.add(ident)
    ctx.cache[key] = ident
    return ident


def _sibling_geometries(
    ctx: _IdentityFlushContext,
    obj: StationaryPointRow,
    algorithm_name: str,
    parent_key: _IdentityKey,
) -> dict[str, GeometryRow]:
    """Return sibling geometries keyed by their `algorithm_name` identity value.

    Siblings are other stationary points sharing the parent identity
    `parent_key`, including ones added earlier in the same flush. One geometry
    is returned per identity value.
    """
    siblings = dict(ctx.pending_siblings.get((parent_key, algorithm_name), {}))
    parent_ident = ctx.cache[parent_key]
    if parent_ident in ctx.session.new:
        return siblings

    ident = aliased(IdentityRow)
    link = aliased(IdentityStationaryLink)
    parent_link = aliased(IdentityStationaryLink)
    stmt = (
        select(ident.value, GeometryRow)
        .join(link, col(link.identity_id) == col(ident.id))
        .join(parent_link, col(parent_link.stationary_id) == col(link.stationary_id))
        .join(
            StationaryPointRow,
            col(StationaryPointRow.id) == col(link.stationary_id),
        )
        .join(GeometryRow, col(GeometryRow.id) == col(StationaryPointRow.geometry_id))
        .where(
            col(ident.algorithm_name) == algorithm_name,
            col(parent_link.identity_id) == parent_ident.id,
            col(StationaryPointRow.id) != obj.id,
        )
    )
    for value, geo_row in ctx.session.exec(stmt):
        siblings.setdefault(value, geo_row)
    return siblings


def _generate_identity(
    algorithm: IdentityAlgorithm,
    geo_row: GeometryRow,
    other_geos: dict[str, GeometryRow] | None,
) -> str | None:
    """Run `algorithm` on `geo_row`, warning and returning None on failure."""
    try:
        value = algorithm.identity_fn(geo_row, other_geos or None)
    except _IDENTITY_ERRORS as err:
        reason = f"{type(err).__name__}: {err}"
    else:
        if value:
            return value
        reason = "empty identity value."
    msg = f"Skipping {algorithm.name!r} identity for GeometryRow {geo_row.id}: {reason}"
    warnings.warn(msg, IdentityGenerationWarning, stacklevel=2)
    return None


def _attach_identities(ctx: _IdentityFlushContext, obj: StationaryPointRow) -> None:
    """Generate and attach an identity for every registered algorithm to `obj`.

    Algorithms with a parent (e.g. SMILES, with InChI as parent) are passed
    `other_geos`: one geometry per existing identity value among stationary
    points sharing the parent identity. If an algorithm fails, a warning is
    issued and its identity is skipped. Algorithms marked `minima_only` are
    skipped for saddle points (nonzero `order`).
    """
    geo_row = _resolve_geometry(ctx.session, obj)
    if geo_row is None:
        # Without a geometry there is nothing to compute identities from
        return

    keys: dict[str, _IdentityKey] = {}
    for algorithm in ctx.algorithms:
        if algorithm.minima_only and obj.order != 0:
            continue
        name = algorithm.name
        parent = algorithm.parent
        parent_key = keys.get(parent.name) if parent is not None else None

        other_geos = None
        if parent_key is not None:
            other_geos = _sibling_geometries(ctx, obj, name, parent_key)

        value = _generate_identity(algorithm, geo_row, other_geos)
        if value is None:
            continue

        ident = _get_or_create_identity(ctx, name, value)
        if all(link.identity is not ident for link in obj.identity_links):
            obj.identity_links.append(IdentityStationaryLink(identity=ident))
        keys[name] = (name, value)
        if parent_key is not None:
            pending = ctx.pending_siblings.setdefault((parent_key, name), {})
            pending.setdefault(value, geo_row)


def _identity_inputs_changed(obj: StationaryPointRow) -> bool:
    """Return whether the geometry or order of a persisted stationary point changed."""
    state = inspect(obj)
    if state is None:
        return False
    return any(
        state.attrs[name].history.has_changes()
        for name in ("geometry", "geometry_id", "order")
    )


@event.listens_for(AutostorageSession, "before_flush")
def add_registry_identities_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Attach registry identities to new stationary points.

    Generates and attaches an `IdentityRow` for every registered algorithm (e.g.
    InChI, SMILES, Hill formula). Identities of persisted stationary points are
    regenerated if their geometry or order changes.
    """
    new = [obj for obj in session.new if isinstance(obj, StationaryPointRow)]
    changed = [
        obj
        for obj in session.dirty
        if isinstance(obj, StationaryPointRow) and _identity_inputs_changed(obj)
    ]
    if not new and not changed:
        return

    ctx = _IdentityFlushContext(session=session)
    for obj in changed:
        obj.identity_links.clear()
    for obj in new + changed:
        _attach_identities(ctx, obj)
