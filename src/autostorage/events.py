"""SQLAlchemy ORM event listeners for validation and auto-managed identities.

The session-level listeners in this module are registered on `AutostorageSession`
(returned by `Database.session()`), so they do not affect unrelated SQLAlchemy
sessions in the same process.
"""

import warnings
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
import pint
from autogeom import (
    GeometryConversionError,
    PESPoint,
    stationary_point_order,
    ureg,
    vibrational_analysis,
)
from sqlalchemy import event, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, UOWTransaction, aliased
from sqlmodel import Session, col, select

from .identity import IdentityAlgorithm, IdentityAlgorithmRegistry, IdentityResult
from .model_hash import ModelHashAlgorithm, ModelHashAlgorithmRegistry
from .models import (
    GeometryRow,
    GeometryTrajectoryLink,
    IdentityAlgorithmRow,
    IdentityRow,
    IdentityStationaryLink,
    ModelHashAlgorithmRow,
    ModelHashLink,
    ModelHashRow,
    ModelRow,
    PropertyKindRow,
    PropertyValueRow,
    StageRow,
    StageStationaryLink,
    StationaryPointRow,
    StepRow,
    TrajectoryAxisRow,
    TrajectoryRow,
    geometry_hash,
    identity_value_hash,
    stage_hash,
)
from .property import PropertyKindRegistry, hessian_property_kind
from .types import AxisKind


class AutostorageSession(Session):
    """`sqlmodel.Session` with autostorage's validation and identity listeners."""


class IdentityGenerationWarning(UserWarning):
    """An identity algorithm could not generate an identity for a geometry."""


class ModelHashGenerationWarning(UserWarning):
    """A model hash algorithm could not hash a model."""


class StationaryOrderWarning(UserWarning):
    """A stationary point's Hessian does not have the point's `order`."""


# Errors that the built-in identity functions raise for unsupported or unperceivable
# geometries (e.g. metals, no valid Lewis structure, failed InChI generation).
_IDENTITY_ERRORS = (GeometryConversionError, NotImplementedError, ValueError)

# Errors that a model hash function raises for a model it can't hash (e.g.
# keywords that aren't JSON-serializable).
_MODEL_HASH_ERRORS = (TypeError, ValueError, NotImplementedError)

# Model hash values must be shorter than this (portable as an indexed VARCHAR).
MAX_MODEL_HASH_LENGTH = 255


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


def create_model_hash_algorithms(session: Session) -> None:
    """Create or update a row for every registered model hash algorithm."""
    for alg in ModelHashAlgorithmRegistry.algorithms:
        row = session.get(ModelHashAlgorithmRow, alg.name)
        if row is None:
            row = ModelHashAlgorithmRow(name=alg.name, kind=alg.kind)
            session.add(row)
        row.kind = alg.kind
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


@event.listens_for(GeometryRow, "before_insert")
@event.listens_for(GeometryRow, "before_update")
def set_geometry_hash(
    mapper: Mapper[GeometryRow],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GeometryRow,
) -> None:
    """Set `hash`, whose unique index rejects duplicate geometries."""
    target.hash = geometry_hash(target)


@event.listens_for(IdentityRow, "before_insert")
@event.listens_for(IdentityRow, "before_update")
def set_identity_value_hash(
    mapper: Mapper[IdentityRow],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: IdentityRow,
) -> None:
    """Set `value_hash`, which identities are unique and looked up by."""
    target.value_hash = identity_value_hash(target.value)


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


def _has_changes(obj: object, *names: str) -> bool:
    """Return whether any of the attributes `names` of `obj` changed."""
    state = inspect(obj)
    return any(state.attrs[name].history.has_changes() for name in names)


def _link_stage(session: Session, link: StageStationaryLink) -> StageRow | None:
    """Return the stage of `link`, via its relationship or foreign key."""
    if link.stage is not None:
        return link.stage
    if link.stage_id is not None:
        return session.get(StageRow, link.stage_id)
    return None


def _link_point(
    session: Session, link: StageStationaryLink | IdentityStationaryLink
) -> StationaryPointRow | None:
    """Return the stationary point of `link`, via its relationship or foreign key."""
    if link.stationary is not None:
        return link.stationary
    if link.stationary_id is not None:
        return session.get(StationaryPointRow, link.stationary_id)
    return None


def _live_stage_links(session: Session, stage: StageRow) -> list[StageStationaryLink]:
    """Return the links of `stage` that will remain after this flush.

    A link removed from its point's `stage_links` stays in the stage's list until
    the flush deletes it as an orphan, so it is left out here.
    """
    return [
        link
        for link in stage.stationary_links
        if link not in session.deleted
        and not (
            link.stationary is None
            and inspect(link).attrs["stationary"].history.deleted
        )
    ]


def _stages_changed_by(session: Session, obj: object) -> list[StageRow | None]:
    """Return the stages whose content a new or dirty `obj` changes."""
    if isinstance(obj, StageRow):
        changed = obj in session.new or _has_changes(obj, "stationary_links", "is_ts")
        return [obj] if changed else []
    if isinstance(obj, StageStationaryLink):
        if obj in session.new:
            return [_link_stage(session, obj)]
        fields = ("count", "stage", "stage_id", "stationary", "stationary_id")
        if not _has_changes(obj, *fields):
            return []
        old_stages = inspect(obj).attrs["stage"].history.deleted
        return [_link_stage(session, obj), *old_stages]
    if isinstance(obj, StationaryPointRow):
        removed = inspect(obj).attrs["stage_links"].history.deleted
        return [_link_stage(session, link) for link in removed]
    return []


def _changed_stages(session: Session) -> list[StageRow]:
    """Return new stages, and stages whose links or `is_ts` changed in this flush.

    A stage that loses a link only because its point is deleted is not included:
    stages are kept when their points are deleted.
    """
    candidates = [
        stage
        for obj in (*session.new, *session.dirty)
        for stage in _stages_changed_by(session, obj)
    ]
    for obj in session.deleted:
        if isinstance(obj, StageStationaryLink):
            point = _link_point(session, obj)
            if point is None or point not in session.deleted:
                candidates.append(_link_stage(session, obj))
    stages = {
        id(stage): stage
        for stage in candidates
        if stage is not None and stage not in session.deleted
    }
    return list(stages.values())


@event.listens_for(AutostorageSession, "before_flush")
def verify_stage_points_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Verify that each new or changed stage has a point, and a TS stage just one.

    A TS stage holds exactly one point, with count 1.
    """
    for stage in _changed_stages(session):
        links = _live_stage_links(session, stage)
        if not links:
            msg = f"StageRow {stage.id} has no stationary points."
            raise ValueError(msg)
        if stage.is_ts and (len(links) != 1 or links[0].count != 1):
            counts = [link.count for link in links]
            msg = (
                f"TS StageRow {stage.id} must hold exactly one stationary point "
                f"with count 1, but has counts {counts}."
            )
            raise ValueError(msg)


@event.listens_for(AutostorageSession, "before_flush")
def set_stage_hash_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Set `hash` on new or changed stages; its unique index rejects duplicates.

    Runs before the flush, since a stage's links are separate rows that a mapper
    "before_insert" hook can't see.
    """
    for stage in _changed_stages(session):
        links = _live_stage_links(session, stage)
        pairs = [(link.point_id, link.count) for link in links]
        stage.hash = stage_hash(pairs, is_ts=stage.is_ts)


def _step_stage(session: Session, step: StepRow, which: str) -> StageRow | None:
    """Return `step.stage<which>`, via its relationship or foreign key."""
    stage = getattr(step, f"stage{which}")
    if stage is not None:
        return stage
    stage_id = getattr(step, f"stage_id{which}")
    return None if stage_id is None else session.get(StageRow, stage_id)


def _stage_composition(
    session: Session, stage: StageRow
) -> tuple[Counter[str], int] | None:
    """Return the element counts and total charge of `stage`, weighted by counts.

    Returns `None` if a point or geometry is missing (the database rejects those).
    """
    elements: Counter[str] = Counter()
    charge = 0
    for link in _live_stage_links(session, stage):
        point = _link_point(session, link)
        geo_row = None if point is None else _resolve_geometry(session, point)
        if geo_row is None:
            return None
        for symbol in geo_row.symbols:
            elements[symbol] += link.count
        charge += link.count * geo_row.charge
    return elements, charge


def _composition_difference(
    reference: tuple[Counter[str], int], other: tuple[Counter[str], int]
) -> str:
    """Describe how `other` differs from `reference` (e.g. ``H: -1, charge: +1``)."""
    (ref_elements, ref_charge), (elements, charge) = reference, other
    diffs = {
        symbol: elements[symbol] - ref_elements[symbol]
        for symbol in sorted(ref_elements.keys() | elements.keys())
    }
    diffs["charge"] = charge - ref_charge
    return ", ".join(f"{key}: {diff:+d}" for key, diff in diffs.items() if diff)


@event.listens_for(AutostorageSession, "before_flush")
def verify_step_balance_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Verify that a step's stages have the same elements and total charge.

    Runs for new or changed steps, and the steps of changed stages. Elements and
    charges are summed over each stage's points, times their counts. Spin is not
    checked, since steps may be spin-forbidden.
    """
    steps = {id(step): step for step in _pending(session, StepRow)}
    for stage in _changed_stages(session):
        steps.update((id(step), step) for step in stage.steps)

    for step in steps.values():
        if step in session.deleted:
            continue
        stages = {
            which: _step_stage(session, step, which) for which in ("1", "2", "_ts")
        }
        compositions = {
            which: _stage_composition(session, stage)
            for which, stage in stages.items()
            if stage is not None
        }
        reference = compositions.get("1")
        if reference is None:
            continue
        for which in ("2", "_ts"):
            other = compositions.get(which)
            if other is not None and other != reference:
                diff = _composition_difference(reference, other)
                msg = (
                    f"StepRow {step.id} is unbalanced: stage{which} differs from "
                    f"stage1 by {diff}."
                )
                raise ValueError(msg)


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


def _is_hessian(obj: object) -> bool:
    return (
        isinstance(obj, PropertyValueRow)
        and _property_kind_name(obj) == hessian_property_kind.name
    )


def _hessians(session: Session, geo_row: GeometryRow) -> list[PropertyValueRow]:
    """Return the Hessians stored, or pending, for `geo_row`."""
    pending = [
        obj
        for obj in session.new
        if isinstance(obj, PropertyValueRow)
        and (obj.geometry is geo_row or obj.geometry_id == geo_row.id)
    ]
    # Pending rows are usually in `geo_row.properties` too, so deduplicate by identity
    unique = {id(p): p for p in (*geo_row.properties, *pending)}
    return [p for p in unique.values() if _is_hessian(p) and p not in session.deleted]


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
        if geo_row is not None and not _hessians(session, geo_row):
            msg = (
                "StationaryPointRow cannot be marked as validated without a "
                f"Hessian attached to its geometry (geometry_id={geo_row.id})"
            )
            raise ValueError(msg)


@event.listens_for(AutostorageSession, "before_flush")
def validate_stationary_order_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Set `is_validated` from whether the Hessians have the stationary point's order.

    Runs for new or modified stationary points, and for those whose geometry gains,
    changes, or loses a Hessian. A point is validated if every Hessian of its geometry
    has `order` negative eigenvalues (`autogeom.stationary_point_order`); otherwise it
    is not, with a `StationaryOrderWarning`. Pseudo stationary points are skipped.
    """
    pending = _pending(session, StationaryPointRow)
    points = {id(stp): stp for stp in pending}
    for obj in (*session.new, *session.dirty, *session.deleted):
        if _is_hessian(obj) and (geo_row := _resolve_geometry(session, obj)):
            points.update({id(stp): stp for stp in geo_row.stationary_points})

    for stp in points.values():
        geo_row = _resolve_geometry(session, stp)
        if stp.is_pseudo or geo_row is None or stp in session.deleted:
            continue
        hessians = _hessians(session, geo_row)
        if not hessians:
            # A pending point marked as validated is rejected by
            # `verify_valid_stationary_has_hessian`
            if stp not in pending:
                stp.is_validated = False
            continue
        orders = [_hessian_order(geo_row, hess) for hess in hessians]
        stp.is_validated = all(order == stp.order for order in orders)
        if not stp.is_validated:
            msg = (
                f"StationaryPointRow {stp.id} has order {stp.order}, but the "
                f"Hessians of GeometryRow {geo_row.id} have orders {orders}; "
                "it is not validated."
            )
            warnings.warn(msg, StationaryOrderWarning, stacklevel=2)


def _hessian_order(geo_row: GeometryRow, hess: PropertyValueRow) -> int | None:
    """Return the stationary point order of `hess`, or `None` if it is invalid."""
    try:
        point = PESPoint(
            geometry=geo_row, hessian=np.asarray(hess.value, dtype=np.float64)
        )
    except ValueError:
        return None
    return stationary_point_order(vibrational_analysis(point))


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
                col(IdentityRow.value_hash) == identity_value_hash(value),
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


def _is_permutation(atom_map: object, natoms: int) -> bool:
    """Return whether `atom_map` lists the indices ``0..natoms-1`` in any order."""
    if not isinstance(atom_map, (list, tuple)):
        return False
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in atom_map):
        return False
    return sorted(atom_map) == list(range(natoms))


def _generate_identity(
    algorithm: IdentityAlgorithm,
    geo_row: GeometryRow,
    other_geos: dict[str, GeometryRow] | None,
) -> IdentityResult | None:
    """Run `algorithm` on `geo_row`, warning and returning None on failure.

    An empty value, or an `atom_map` that isn't a permutation of the geometry's
    atoms, also counts as a failure.
    """
    try:
        result = algorithm.identity_fn(geo_row, None, other_geos or None)
    except _IDENTITY_ERRORS as err:
        reason = f"{type(err).__name__}: {err}"
    else:
        if not isinstance(result, IdentityResult):
            result = IdentityResult(result)
        atom_map = result.atom_map
        if not result.value:
            reason = "empty identity value."
        elif atom_map is not None and not _is_permutation(
            list(atom_map), geo_row.atom_count
        ):
            reason = (
                f"atom_map {list(atom_map)} is not a permutation of the "
                f"{geo_row.atom_count} atoms."
            )
        else:
            return result
    msg = f"Skipping {algorithm.name!r} identity for GeometryRow {geo_row.id}: {reason}"
    warnings.warn(msg, IdentityGenerationWarning, stacklevel=2)
    return None


def _attach_identities(ctx: _IdentityFlushContext, obj: StationaryPointRow) -> None:
    """Generate and attach an identity for every registered algorithm to `obj`.

    Algorithms with a parent (e.g. SMILES, with InChI as parent) are passed
    `other_geos`: one geometry per existing identity value among stationary
    points sharing the parent identity. If an algorithm fails, a warning is
    issued and its identity is skipped. Algorithms that do not apply to
    stationary points of the given order are skipped.
    """
    geo_row = _resolve_geometry(ctx.session, obj)
    if geo_row is None:
        # Without a geometry there is nothing to compute identities from
        return

    keys: dict[str, _IdentityKey] = {}
    for algorithm in ctx.algorithms:
        if not algorithm.applies_to(obj.order):
            continue
        name = algorithm.name
        parent = algorithm.parent
        parent_key = keys.get(parent.name) if parent is not None else None

        other_geos = None
        if parent_key is not None:
            other_geos = _sibling_geometries(ctx, obj, name, parent_key)

        result = _generate_identity(algorithm, geo_row, other_geos)
        if result is None:
            continue

        value = result.value
        ident = _get_or_create_identity(ctx, name, value)
        if all(link.identity is not ident for link in obj.identity_links):
            atom_map = None if result.atom_map is None else list(result.atom_map)
            link = IdentityStationaryLink(
                identity=ident, atom_map=atom_map, algorithm_cache=result.cache
            )
            obj.identity_links.append(link)
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


def _link_algorithm_name(session: Session, link: IdentityStationaryLink) -> str | None:
    """Return the algorithm name of `link`'s identity, via relationship or key."""
    ident = link.identity
    if ident is None and link.identity_id is not None:
        ident = session.get(IdentityRow, link.identity_id)
    return None if ident is None else ident.algorithm_name


@event.listens_for(AutostorageSession, "before_flush")
def verify_identity_atom_maps_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Check that a new or changed link's `atom_map` permutes its point's atoms.

    Raises:
        ValueError: If an `atom_map` isn't a permutation of the point geometry's
            atom indices.
    """
    for link in _pending(session, IdentityStationaryLink):
        if link.atom_map is None:
            continue
        if link not in session.new and not _has_changes(link, "atom_map"):
            continue
        point = _link_point(session, link)
        if point is None:
            continue
        geo_row = _resolve_geometry(session, point)
        if geo_row is None or _is_permutation(link.atom_map, geo_row.atom_count):
            continue
        algorithm_name = _link_algorithm_name(session, link)
        msg = (
            f"atom_map {link.atom_map} of the {algorithm_name!r} identity of "
            f"StationaryPointRow {point.id} is not a permutation of its "
            f"{geo_row.atom_count} atoms."
        )
        raise ValueError(msg)


@dataclass
class _ModelHashFlushContext:
    """Per-flush cache of pending `ModelHashRow`s, keyed by algorithm name and value.

    Autoflush is suppressed while "before_flush" handlers run, so hashes created
    earlier in the same flush are not visible to queries.
    """

    session: Session
    cache: dict[tuple[str, str], ModelHashRow] = field(default_factory=dict)


def _get_or_create_model_hash(
    ctx: _ModelHashFlushContext, algorithm_name: str, value: str
) -> ModelHashRow:
    """Look up a pending or persisted model hash, creating one if none exists."""
    key = (algorithm_name, value)
    hash_row = ctx.cache.get(key)
    if hash_row is None:
        hash_row = ctx.session.exec(
            select(ModelHashRow).where(
                col(ModelHashRow.algorithm_name) == algorithm_name,
                col(ModelHashRow.value) == value,
            )
        ).one_or_none()
    if hash_row is None:
        hash_row = ModelHashRow(algorithm_name=algorithm_name, value=value)
        ctx.session.add(hash_row)
    ctx.cache[key] = hash_row
    return hash_row


def _generate_model_hash(algorithm: ModelHashAlgorithm, row: ModelRow) -> str | None:
    """Run `algorithm` on `row`, warning and returning None on failure."""
    try:
        value = algorithm.hash(row)
    except _MODEL_HASH_ERRORS as err:
        reason = f"{type(err).__name__}: {err}"
    else:
        if not value:
            reason = "empty hash value."
        elif len(value) >= MAX_MODEL_HASH_LENGTH:
            reason = (
                f"hash value has {len(value)} characters "
                f"(the limit is under {MAX_MODEL_HASH_LENGTH})."
            )
        else:
            return value
    msg = f"Skipping {algorithm.name!r} hash for ModelRow {row.id}: {reason}"
    warnings.warn(msg, ModelHashGenerationWarning, stacklevel=2)
    return None


def _attach_model_hashes(ctx: _ModelHashFlushContext, row: ModelRow) -> None:
    """Link `row` to a hash row for every registered algorithm that applies.

    If an algorithm fails, a warning is issued and its hash is skipped.
    """
    for algorithm in ModelHashAlgorithmRegistry.algorithms:
        if not algorithm.applies_to(row.program):
            continue
        value = _generate_model_hash(algorithm, row)
        if value is None:
            continue
        hash_row = _get_or_create_model_hash(ctx, algorithm.name, value)
        if all(link.hash is not hash_row for link in row.hash_links):
            row.hash_links.append(ModelHashLink(hash=hash_row))


def _model_hash_inputs_changed(row: ModelRow) -> bool:
    """Return whether the program, method, basis or keywords of a model changed."""
    state = inspect(row)
    if state is None:
        return False
    return any(
        state.attrs[name].history.has_changes()
        for name in ("program", "method", "basis", "keywords")
    )


@event.listens_for(AutostorageSession, "before_flush")
def add_model_hashes_before_flush(
    session: Session,
    flush_context: UOWTransaction,  # noqa: ARG001
    instances: object,  # noqa: ARG001
) -> None:
    """Attach registry model hashes to new models.

    Generates and attaches a `ModelHashRow` for every registered algorithm that
    applies to the model's program (e.g. `minimal@1`, `exact@1`). Hashes of
    persisted models are regenerated if their program, method, basis or
    keywords change.
    """
    new = [obj for obj in session.new if isinstance(obj, ModelRow)]
    changed = [
        obj
        for obj in session.dirty
        if isinstance(obj, ModelRow) and _model_hash_inputs_changed(obj)
    ]
    if not new and not changed:
        return

    ctx = _ModelHashFlushContext(session=session)
    for row in changed:
        row.hash_links.clear()
    for row in new + changed:
        _attach_model_hashes(ctx, row)
