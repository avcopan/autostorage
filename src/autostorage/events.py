"""SQLAlchemy ORM event listeners for validation and auto-managed identities.

The session-level listeners in this module are registered on `AutostorageSession`
(returned by `Database.session()`), so they do not affect unrelated SQLAlchemy
sessions in the same process.
"""

import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
from autogeom import GeometryConversionError
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
    TrajectoryRow,
)
from .property import PropertyKindRegistry, hessian_property_kind


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
    rows = {row.name: row for row in session.exec(select(IdentityAlgorithmRow))}
    for alg in _ordered_algorithms():
        parent_id = None
        if alg.parent is not None:
            parent_id = rows[alg.parent.name].id

        row = rows.get(alg.name)
        if row is None:
            row = IdentityAlgorithmRow(
                name=alg.name, kind=alg.kind, parent_algorithm_id=parent_id
            )
            session.add(row)
        else:
            row.kind = alg.kind
            row.parent_algorithm_id = parent_id
        # Flush so the primary key is available to child algorithms
        session.flush()
        rows[alg.name] = row
    session.commit()


def create_property_kinds(session: Session) -> None:
    """Create a row for every registered property kind that is missing one."""
    for prop_kind in PropertyKindRegistry.property_kinds:
        if session.get(PropertyKindRow, prop_kind.name) is None:
            session.add(PropertyKindRow(name=prop_kind.name))
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
    """Validate property values against their kind and cast them to its dtype."""
    for obj in _pending(session, PropertyValueRow):
        name = _property_kind_name(obj)
        geo_row = _resolve_geometry(session, obj)
        if name is None or geo_row is None:
            # Missing foreign keys are rejected by the database
            continue

        prop_kind = PropertyKindRegistry.get(name)
        try:
            value = np.asarray(obj.value, dtype=prop_kind.dtype)
        except (TypeError, ValueError):
            # Raised for ragged/inhomogeneous or non-numeric values
            value = None
        if value is None or not prop_kind.validation_fn(value, geo_row):
            msg = (
                f"Property {name!r} for GeometryRow {geo_row.id} and "
                f"CalculationRow {obj.calculation_id} does not match the "
                "expected shape."
            )
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
    session: Session, link: GeometryTrajectoryLink
) -> TrajectoryRow | None:
    """Return the trajectory of `link`, via its relationship or foreign key."""
    if link.trajectory is not None:
        return link.trajectory
    if link.trajectory_id is not None:
        return session.get(TrajectoryRow, link.trajectory_id)
    return None


type _IdentityKey = tuple[int, str]
"""An identity's `(algorithm_id, value)`, unique among `IdentityRow`s."""


@dataclass
class _IdentityFlushContext:
    """Per-flush state shared by the identity-resolution helpers below.

    Autoflush is suppressed while "before_flush" handlers run, so identities
    created earlier in the same flush are not visible to queries. They are
    cached here, keyed by algorithm id and value, so that repeated lookups reuse
    the pending row instead of creating a duplicate that would collide with the
    `(algorithm_id, value)` unique constraint.
    """

    session: Session
    algorithm_ids: dict[str, int]
    algorithms: list[IdentityAlgorithm] = field(
        default_factory=lambda: list(_ordered_algorithms())
    )
    cache: dict[_IdentityKey, IdentityRow] = field(default_factory=dict)
    # Geometries of stationary points added in this flush, keyed by
    # (parent identity key, algorithm id) and then by their identity value
    pending_siblings: dict[tuple[_IdentityKey, int], dict[str, GeometryRow]] = field(
        default_factory=dict
    )


def _get_or_create_identity(
    ctx: _IdentityFlushContext, algorithm_id: int, value: str
) -> IdentityRow:
    """Look up a pending or persisted identity, creating one if none exists."""
    key = (algorithm_id, value)
    ident = ctx.cache.get(key)
    if ident is None:
        ident = ctx.session.exec(
            select(IdentityRow).where(
                col(IdentityRow.algorithm_id) == algorithm_id,
                col(IdentityRow.value) == value,
            )
        ).one_or_none()
    if ident is None:
        ident = IdentityRow(algorithm_id=algorithm_id, value=value)
        ctx.session.add(ident)
    ctx.cache[key] = ident
    return ident


def _sibling_geometries(
    ctx: _IdentityFlushContext,
    obj: StationaryPointRow,
    algorithm_id: int,
    parent_key: _IdentityKey,
) -> dict[str, GeometryRow]:
    """Return sibling geometries keyed by their `algorithm_id` identity value.

    Siblings are other stationary points sharing the parent identity
    `parent_key`, including ones added earlier in the same flush. One geometry
    is returned per identity value.
    """
    siblings = dict(ctx.pending_siblings.get((parent_key, algorithm_id), {}))
    parent_ident = ctx.cache[parent_key]
    if parent_ident.id is None:
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
            col(ident.algorithm_id) == algorithm_id,
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
    issued and its identity is skipped.
    """
    geo_row = _resolve_geometry(ctx.session, obj)
    if geo_row is None:
        # Without a geometry there is nothing to compute identities from
        return

    keys: dict[str, _IdentityKey] = {}
    for algorithm in ctx.algorithms:
        alg_id = ctx.algorithm_ids[algorithm.name]
        parent = algorithm.parent
        parent_key = keys.get(parent.name) if parent is not None else None

        other_geos = None
        if parent_key is not None:
            other_geos = _sibling_geometries(ctx, obj, alg_id, parent_key)

        value = _generate_identity(algorithm, geo_row, other_geos)
        if value is None:
            continue

        ident = _get_or_create_identity(ctx, alg_id, value)
        if ident not in obj.identities:
            obj.identities.append(ident)
        keys[algorithm.name] = (alg_id, value)
        if parent_key is not None:
            pending = ctx.pending_siblings.setdefault((parent_key, alg_id), {})
            pending.setdefault(value, geo_row)


def _geometry_changed(obj: StationaryPointRow) -> bool:
    """Return whether the geometry of a persisted stationary point was changed."""
    state = inspect(obj)
    if state is None:
        return False
    return any(
        state.attrs[name].history.has_changes() for name in ("geometry", "geometry_id")
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
    regenerated if their geometry is reassigned.
    """
    new = [obj for obj in session.new if isinstance(obj, StationaryPointRow)]
    changed = [
        obj
        for obj in session.dirty
        if isinstance(obj, StationaryPointRow) and _geometry_changed(obj)
    ]
    if not new and not changed:
        return

    algorithm_ids = {
        row.name: row.id
        for row in session.exec(select(IdentityAlgorithmRow))
        if row.id is not None
    }
    ctx = _IdentityFlushContext(session=session, algorithm_ids=algorithm_ids)
    for obj in changed:
        obj.identities.clear()
    for obj in new + changed:
        _attach_identities(ctx, obj)
