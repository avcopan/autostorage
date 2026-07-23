"""Autostorage database events / listeners."""

from typing import Any

import numpy as np
from automol import Algorithm, geom
from sqlalchemy import event, tuple_
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, object_session
from sqlmodel import Integer, Session, cast, func, select

from .exc import ResultShapeError
from .models import (
    GeometryRow,
    GradientRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
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

    # Validate that all Hessians on this geometry agree on order
    if geometry.hessians:
        orders = {h.order for h in geometry.hessians if h.order is not None}
        if len(orders) > 1:
            msg = f"Geometry Hessians do not agree on order. {orders = }."
            raise ValueError(msg)

        # If they agree, validate the stationary points against that order
        if orders and geometry.stationary_points:
            expected_order = orders.pop()
            for stationary in geometry.stationary_points:
                if stationary.order == expected_order:
                    stationary.is_valid = True
                else:
                    stationary.is_valid = False


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
    return next(
        (i for i in matched_peer.identities if i.kind == Algorithm.IRMSD.kind), None
    )


@event.listens_for(Session, "before_flush")
def assign_conformer_ids(session: Session, flush_context: Any, instances: Any) -> None:  # noqa: ANN401, ARG001
    """Assign a shared conformer-group identity to duplicate stationary points."""
    pending_items: list[tuple[StationaryPointRow, IdentityRow]] = []

    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue
        if any(ident.kind == Algorithm.IRMSD.kind for ident in obj.identities):
            continue

        inchi = next(
            (i for i in obj.identities if i.algorithm == Algorithm.RDKIT_INCHI), None
        )
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
