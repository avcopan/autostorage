"""Autostorage database events / listeners."""

from collections.abc import Iterable
from typing import Any

import numpy as np
from automol import Algorithm, geom
from sqlalchemy import event, tuple_
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, object_session
from sqlalchemy.orm.attributes import get_history
from sqlmodel import Integer, Session, cast, func, select

from .exc import ResultShapeError
from .models import (
    GeometryRow,
    GradientRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
    StageRow,
    StationaryPointRow,
    StepRow,
)


def _resolve_geometry(
    target: GradientRow | HessianRow | StationaryPointRow,
) -> GeometryRow | None:
    """Return the target's geometry, resolving it via the session if unattached.

    Setting only `geometry_id` (without `.geometry`) leaves the relationship
    unpopulated until the ORM syncs it, which would otherwise let shape/order
    validation be skipped for a row that does have a geometry.
    """
    geometry = target.geometry
    if geometry is None and target.geometry_id is not None:
        session = object_session(target)
        if session is not None:
            geometry = session.get(GeometryRow, target.geometry_id)
    return geometry


@event.listens_for(GradientRow, "before_insert")
@event.listens_for(GradientRow, "before_update")
def verify_gradient_shape(
    mapper: Mapper,  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GradientRow,
) -> None:
    """Verify shape of the Gradient array before saving to the database."""
    geometry = _resolve_geometry(target)
    if geometry is None:
        return

    expected = (3 * geometry.atom_count,)
    actual = np.shape(target.value)

    if actual != expected:
        raise ResultShapeError(target, actual, expected)


@event.listens_for(HessianRow, "before_insert")
@event.listens_for(HessianRow, "before_update")
def verify_hessian_shape(
    mapper: Mapper,  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: HessianRow,
) -> None:
    """Verify shape of the Hessian matrix before saving to DB."""
    geometry = _resolve_geometry(target)
    if geometry is None:
        return

    expected_dim = 3 * geometry.atom_count
    expected = (expected_dim, expected_dim)
    actual = np.shape(target.value)

    if actual != expected:
        raise ResultShapeError(target, actual, expected)


def _recompute_geometry_stationary_validity(
    geometry: GeometryRow, *, excluding: Iterable[HessianRow] = ()
) -> None:
    """Recompute `StationaryPointRow.is_valid` for a geometry from its Hessians.

    Shared by the insert/update/delete listeners so order-consensus is
    recomputed identically regardless of which change triggered it.

    Parameters
    ----------
    geometry
        Geometry whose Hessians and stationary points to reconcile.
    excluding, optional
        Hessian rows to leave out of consensus (e.g. ones pending deletion —
        `geometry.hessians` still contains them at `before_flush` time,
        since the DELETE hasn't been issued yet).
    """
    excluded_ids = {id(h) for h in excluding}
    hessians = [h for h in geometry.hessians if id(h) not in excluded_ids]
    if not hessians:
        return

    orders = {h.order for h in hessians if h.order is not None}
    if len(orders) > 1:
        msg = f"Geometry Hessians do not agree on order. {orders = }."
        raise ValueError(msg)

    if orders and geometry.stationary_points:
        expected_order = orders.pop()
        for stationary in geometry.stationary_points:
            stationary.is_valid = stationary.order == expected_order


@event.listens_for(StationaryPointRow, "before_insert")
@event.listens_for(StationaryPointRow, "before_update")
@event.listens_for(HessianRow, "before_insert")
@event.listens_for(HessianRow, "before_update")
def validate_geometry_orders(
    mapper: Mapper,  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: StationaryPointRow | HessianRow,
) -> None:
    """Ensure StationaryPoint and Hessian orders align."""
    geometry = _resolve_geometry(target)
    if geometry is None:
        return
    _recompute_geometry_stationary_validity(geometry)


@event.listens_for(Session, "before_flush")
def revalidate_geometry_orders_on_hessian_delete(
    session: Session,
    flush_context: Any,  # noqa: ANN401, ARG001
    instances: Any,  # noqa: ANN401, ARG001
) -> None:
    """Recompute order consensus for a geometry when one of its Hessians is deleted.

    `validate_geometry_orders` only runs on Hessian insert/update, so
    `StationaryPointRow.is_valid` flags could go stale after the Hessian
    that established consensus order is removed; this closes that gap.

    Note
    ----
    Implemented as a session-level `before_flush` listener, not a
    mapper-level `before_delete` one: SQLAlchemy silently drops attribute
    changes made to *other*, already-clean objects from within mapper-level
    delete events (they aren't part of that object's already-computed flush
    plan) — the same reason `add_inchi_identities`/`assign_conformer_ids`
    below are `before_flush` listeners rather than mapper-level ones.
    """
    deleted_hessians = [obj for obj in session.deleted if isinstance(obj, HessianRow)]
    if not deleted_hessians:
        return

    geometries = {h.geometry_id: h.geometry for h in deleted_hessians if h.geometry}
    for geometry in geometries.values():
        excluding = [h for h in deleted_hessians if h.geometry_id == geometry.id]
        _recompute_geometry_stationary_validity(geometry, excluding=excluding)


_IMMUTABLE_GEOMETRY_FIELDS = ("symbols", "coordinates")


@event.listens_for(GeometryRow, "before_update")
def verify_geometry_immutable_fields(
    mapper: Mapper,  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GeometryRow,
) -> None:
    """Reject changes to `symbols`/`coordinates` on an already-persisted geometry.

    `charge`/`spin` remain mutable; only the fields defining the geometry's
    identity are locked once inserted. Without this, an in-place edit to an
    already-persisted geometry would silently invalidate any Gradient/Hessian
    shape checks already run against it.
    """
    for attr in _IMMUTABLE_GEOMETRY_FIELDS:
        history = get_history(target, attr)
        if history.added or history.deleted:
            msg = f"GeometryRow.{attr} cannot be changed after insert."
            raise ValueError(msg)


@event.listens_for(Session, "before_flush")
def add_inchi_identities(session: Session, flush_context: Any, instances: Any) -> None:  # noqa: ANN401, ARG001
    """Attach InChI and SMILES identities to new stationary point rows before flush."""
    pending_items = []
    inchi_lookups = []

    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue
        try:
            inchi = IdentityRow.from_geometry(
                geo=obj.geometry,
                algorithm=Algorithm.RDKIT_INCHI,
            )
            pending_items.append((obj, inchi))
            inchi_lookups.append((inchi.algorithm, inchi.value))
        except ValueError:
            continue

    if not pending_items:
        return

    stmt = select(IdentityRow).where(
        tuple_(IdentityRow.algorithm, IdentityRow.value).in_(inchi_lookups)  # ty:ignore[invalid-argument-type]
    )
    existing_rows = session.exec(stmt).all()

    identity_map = {(r.algorithm, r.value): r for r in existing_rows}

    for obj, inchi in pending_items:
        lookup_key = (inchi.algorithm, inchi.value)
        existing = identity_map.get(lookup_key)

        if existing:
            obj.identities.append(existing)
            continue

        obj.identities.append(inchi)
        identity_map[lookup_key] = inchi

        try:
            smiles = IdentityRow.from_geometry(
                obj.geometry, algorithm=Algorithm.RDKIT_SMILES
            )
            smiles_extra = IdentityExtraRow(
                identity=inchi, attribute="smiles", value=smiles.value
            )

            session.add(smiles_extra)

        except ValueError:
            continue


def _matching_conformer_identity(
    obj: StationaryPointRow, inchi: IdentityRow
) -> IdentityRow | None:
    """Find the conformer identity of a geometric duplicate among InChI peers."""
    peers = [c for c in inchi.stationary_points if c is not obj]
    if not peers:
        return None

    matches = geom.is_duplicate_conformer(obj.geometry, [c.geometry for c in peers])
    match_idx = next((i for i, m in enumerate(matches) if m), None)
    if match_idx is None:
        return None

    matched_peer = peers[match_idx]
    return matched_peer.identity(kind=Algorithm.IRMSD.kind)


@event.listens_for(Session, "before_flush")
def assign_conformer_ids(session: Session, flush_context: Any, instances: Any) -> None:  # noqa: ANN401, ARG001
    """Assign a shared conformer-group identity to duplicate stationary points."""
    pending_items: list[tuple[StationaryPointRow, IdentityRow]] = []

    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue
        if obj.identity(kind=Algorithm.IRMSD.kind) is not None:
            continue

        inchi = obj.identity(algorithm=Algorithm.RDKIT_INCHI)
        if inchi is not None:
            pending_items.append((obj, inchi))

    if not pending_items:
        return

    next_group_id: int | None = None

    for obj, inchi in pending_items:
        match_ident = _matching_conformer_identity(obj, inchi)

        if match_ident is not None:
            obj.identities.append(match_ident)
            continue

        if next_group_id is None:
            # Assumes single-writer semantics, consistent with Database's
            # documented non-thread-safety. If that's violated, IdentityRow's
            # unique_identity constraint (kind, algorithm, value) turns a
            # racing duplicate group id into an IntegrityError at commit
            # rather than a silently merged conformer group.
            current_max = session.exec(
                select(func.max(cast(IdentityRow.value, Integer))).where(
                    IdentityRow.kind == Algorithm.IRMSD.kind
                )
            ).first()
            next_group_id = (current_max or 0) + 1
        else:
            next_group_id += 1

        conformer = IdentityRow.from_value(
            str(next_group_id), algorithm=Algorithm.IRMSD
        )
        obj.identities.append(conformer)


@event.listens_for(StepRow, "before_insert")
@event.listens_for(StepRow, "before_update")
def verify_stage_order_and_barrierless(
    mapper: Mapper,  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: StepRow,
) -> None:
    """Verify order of stage ids in StepRow and determine whether barrierless."""
    stg_id1 = target.stage_id1 or target.stage1.id
    stg_id2 = target.stage_id2 or target.stage2.id

    if not stg_id1 or not stg_id2:
        msg = "Cannot sort stage IDs; IDs aren't assigned to stages."
        raise ValueError(msg)

    if stg_id1 > stg_id2:
        target.stage_id1, target.stage_id2 = stg_id2, stg_id1

    target.is_barrierless = not target.stage_id_ts


def _resolve_stage(target: StepRow, id_attr: str, rel_attr: str) -> StageRow | None:
    """Return one of a StepRow's stages, resolving via session if unattached.

    Mirrors `_resolve_geometry`: setting only the FK id (e.g. `stage_id_ts`)
    without the relationship (`stage_ts`) leaves it unpopulated until the ORM
    syncs it, which would otherwise let this check be skipped for a step
    that does have a linked stage.
    """
    stage = getattr(target, rel_attr)
    if stage is None:
        stage_id = getattr(target, id_attr)
        if stage_id is not None:
            session = object_session(target)
            if session is not None:
                stage = session.get(StageRow, stage_id)
    return stage


@event.listens_for(StepRow, "before_insert")
@event.listens_for(StepRow, "before_update")
def verify_stage_ts_consistency(
    mapper: Mapper,  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: StepRow,
) -> None:
    """Verify is_ts agreement between a StepRow and its linked stages.

    `stage1`/`stage2` must not be transition-state stages; when
    `stage_id_ts` is set, the referenced stage must be one.
    """
    stage1 = _resolve_stage(target, "stage_id1", "stage1")
    stage2 = _resolve_stage(target, "stage_id2", "stage2")
    stage_ts = _resolve_stage(target, "stage_id_ts", "stage_ts")

    if (stage1 is not None and stage1.is_ts) or (stage2 is not None and stage2.is_ts):
        msg = "Step's stage1/stage2 cannot be a transition-state stage."
        raise ValueError(msg)
    if stage_ts is not None and not stage_ts.is_ts:
        msg = "Step's stage_ts must reference a transition-state stage."
        raise ValueError(msg)
