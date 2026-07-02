"""Autostorage database events / listeners."""

from typing import Any

import numpy as np
from sqlalchemy import event, tuple_
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper
from sqlmodel import Session, select

from .exc import ResultShapeError
from .models import (
    GradientRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
    StationaryPointRow,
    StepRow,
)


@event.listens_for(GradientRow, "before_insert")
@event.listens_for(GradientRow, "before_update")
def verify_gradient_shape(
    mapper: Mapper,  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GradientRow,
) -> None:
    """Verify shape of the Gradient array before saving to the database."""
    if not target.geometry:
        return

    expected = (3 * target.geometry.atom_count,)
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
    if not target.geometry:
        return

    expected_dim = 3 * target.geometry.atom_count
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
    # Ensure there is a geometry reference
    geometry = getattr(target, "geometry", None)
    if not geometry:
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
                algorithm="rdkit inchi",
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
            smiles = IdentityRow.from_geometry(obj.geometry, algorithm="rdkit smiles")
            smiles_extra = IdentityExtraRow(
                identity=inchi, attribute="smiles", value=smiles.value
            )

            session.add(smiles_extra)

        except ValueError:
            continue


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
