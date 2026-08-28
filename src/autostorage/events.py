"""SQLAlchemy ORM event listeners for validation and auto-managed identities."""

from typing import Any

from automol import Identity
from automol.ident import Algorithm
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, Session

from .models import (
    GeometryRow,
    GeometryTrajectoryLink,
    GradientRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
    StationaryPointRow,
    StepRow,
)


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
    """Verify is_barrierless consistency with stage_id_ts."""
    if target.stage_id_ts is None:
        if not target.is_barrierless:
            msg = "Barrierless step (stage_id_ts=None) must have is_barrierless=True"
            raise ValueError(msg)
    elif target.is_barrierless:
        msg = (
            "Step with transition state (stage_id_ts!=None) must have "
            "is_barrierless=False"
        )
        raise ValueError(msg)


@event.listens_for(Session, "before_flush")
def verify_gradient_shapes_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Verify gradient shapes match 3 * natoms for all gradients being flushed."""
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, GradientRow):
            continue

        if obj.geometry_id is None:
            continue

        # Load the geometry to get natoms
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        natoms = len(geometry_row.symbols)
        expected_shape = (3 * natoms,)
        actual_shape = obj.value.shape

        if actual_shape != expected_shape:
            msg = (
                f"Gradient shape {actual_shape} does not match expected "
                f"shape {expected_shape} for geometry with {natoms} atoms"
            )
            raise ValueError(msg)


@event.listens_for(Session, "before_flush")
def verify_hessian_shapes_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Verify Hessian shapes match (3 * natoms, 3 * natoms) for all Hessians."""
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, HessianRow):
            continue

        if obj.geometry_id is None:
            continue

        # Load the geometry to get natoms
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        natoms = len(geometry_row.symbols)
        expected_shape = (3 * natoms, 3 * natoms)
        actual_shape = obj.value.shape

        if actual_shape != expected_shape:
            msg = (
                f"Hessian shape {actual_shape} does not match expected "
                f"shape {expected_shape} for geometry with {natoms} atoms"
            )
            raise ValueError(msg)


@event.listens_for(Session, "before_flush")
def verify_valid_stationary_has_hessian(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Verify that stationary points marked as valid have an associated Hessian."""
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, StationaryPointRow):
            continue

        if not obj.is_valid:
            continue

        if obj.geometry_id is None:
            continue

        # Load the geometry to check for hessians
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        if not geometry_row.hessians:
            msg = (
                f"StationaryPointRow cannot be marked as valid without a Hessian "
                f"attached to its geometry (geometry_id={obj.geometry_id})"
            )
            raise ValueError(msg)


@event.listens_for(GeometryTrajectoryLink, "before_insert")
@event.listens_for(GeometryTrajectoryLink, "before_update")
def verify_trajectory_geometry_ndim_insert(
    mapper: Mapper[GeometryTrajectoryLink],  # noqa: ARG001
    connection: Connection,  # noqa: ARG001
    target: GeometryTrajectoryLink,
) -> None:
    """Ensure linked geometry's index length matches trajectory ndim."""
    if target.trajectory is None:
        return

    traj_ndim = target.trajectory.ndim
    index_len = len(target.index) if target.index is not None else None

    if index_len is not None and traj_ndim is not None and index_len != traj_ndim:
        msg = (
            f"Geometry index length {index_len} does not match "
            f"trajectory ndim {traj_ndim}"
        )
        raise ValueError(msg)

    if traj_ndim is None and index_len is not None:
        target.trajectory.ndim = index_len
    elif index_len is None and traj_ndim is not None:
        msg = f"Geometry index is missing but trajectory ndim is {traj_ndim}"
        raise ValueError(msg)


def _find_or_create_identity(session: Session, identity: Identity) -> IdentityRow:
    """Find or create an IdentityRow for the given Identity.

    Checks both the database and pending session inserts.
    """
    # First check the database
    existing = (
        session.query(IdentityRow)
        .filter_by(
            kind=identity.kind,
            algorithm=str(identity.algorithm),
            value=identity.value,
        )
        .first()
    )

    # If not in database, check session.new for pending inserts
    if existing is None:
        for new_obj in session.new:
            if (
                isinstance(new_obj, IdentityRow)
                and new_obj.kind == identity.kind
                and new_obj.algorithm == str(identity.algorithm)
                and new_obj.value == identity.value
            ):
                existing = new_obj
                break

    if existing is None:
        # Create new identity row
        new_identity = IdentityRow(
            kind=identity.kind,
            algorithm=str(identity.algorithm),
            value=identity.value,
        )
        session.add(new_identity)
        return new_identity

    return existing


@event.listens_for(Session, "before_flush")
def add_inchi_identities_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Automatically attach InChI identities to newly inserted stationary points."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        if obj.geometry_id is None or obj.identities:
            continue

        # Load the geometry
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        # Generate InChI identity from geometry
        identity = Identity.from_geometry(geometry_row, algorithm=Algorithm.RDKIT_INCHI)

        # Find or create the identity row
        identity_row = _find_or_create_identity(session, identity)

        # Link the identity to the stationary point
        if identity_row not in obj.identities:
            obj.identities.append(identity_row)


def _find_or_create_identity_extra(
    session: Session, identity: IdentityRow, attribute: str, value: str
) -> IdentityExtraRow | None:
    """Find or create an IdentityExtraRow.

    Checks both the database and pending session inserts. Returns None if the
    extra already exists.
    """
    # Check if the identity has an ID (already in database)
    if identity.id is not None:
        existing = (
            session.query(IdentityExtraRow)
            .filter_by(
                identity_id=identity.id,
                attribute=attribute,
                value=value,
            )
            .first()
        )
        if existing is not None:
            return None  # Already exists in database

    # Check session.new for pending inserts (both for this identity and in general)
    for new_obj in session.new:
        if (
            isinstance(new_obj, IdentityExtraRow)
            and (new_obj.identity is identity or new_obj.identity_id == identity.id)
            and new_obj.attribute == attribute
            and new_obj.value == value
        ):
            return None  # Already pending insertion

    # Create new extra, using the identity relationship
    return IdentityExtraRow(
        identity=identity,
        attribute=attribute,
        value=value,
    )


@event.listens_for(Session, "before_flush")
def add_smiles_extras_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Automatically attach SMILES as IdentityExtraRow to stationary points."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        if obj.geometry_id is None or not obj.identities:
            continue

        # Load the geometry
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        # Generate SMILES from geometry
        try:
            smiles_identity = Identity.from_geometry(
                geometry_row, algorithm=Algorithm.RDKIT_SMILES
            )
            smiles_value = smiles_identity.value
        except Exception:  # noqa: BLE001, S112
            # Skip if SMILES generation fails (e.g., invalid structure)
            continue

        # Get the InChI identity (should exist from add_inchi_identities_before_flush)
        inchi_identity = next(
            (
                ident
                for ident in obj.identities
                if ident.algorithm == str(Algorithm.RDKIT_INCHI)
            ),
            None,
        )

        if inchi_identity is None:
            continue

        # Find or create the SMILES extra
        smiles_extra = _find_or_create_identity_extra(
            session, inchi_identity, "rdkit_smiles", smiles_value
        )

        if smiles_extra is not None:
            session.add(smiles_extra)


@event.listens_for(Session, "before_flush")
def add_hill_extras_before_flush(
    session: Session,
    flush_context: Any,  # noqa: ARG001, ANN401
    instances: Any,  # noqa: ARG001, ANN401
) -> None:
    """Automatically attach Hill formula as IdentityExtraRow to stationary points."""
    for obj in session.new:
        if not isinstance(obj, StationaryPointRow):
            continue

        if obj.geometry_id is None or not obj.identities:
            continue

        # Load the geometry
        geometry_row = session.get(GeometryRow, obj.geometry_id)
        if geometry_row is None:
            continue

        # Generate Hill formula from geometry
        try:
            hill_identity = Identity.from_geometry(
                geometry_row, algorithm=Algorithm.HILL_FORMULA
            )
            hill_value = hill_identity.value
        except Exception:  # noqa: BLE001, S112
            # Skip if Hill formula generation fails (e.g., invalid structure)
            continue

        # Get the InChI identity (should exist from add_inchi_identities_before_flush)
        inchi_identity = next(
            (
                ident
                for ident in obj.identities
                if ident.algorithm == str(Algorithm.RDKIT_INCHI)
            ),
            None,
        )

        if inchi_identity is None:
            continue

        # Find or create the Hill formula extra
        hill_extra = _find_or_create_identity_extra(
            session, inchi_identity, "hill_formula", hill_value
        )

        if hill_extra is not None:
            session.add(hill_extra)
