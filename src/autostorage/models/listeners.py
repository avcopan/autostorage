"""Model listeners."""

from automol import geom
from sqlalchemy import event
from sqlmodel import Session, select

from ..calcn import calculation_hash, hash_registry
from .calculation import CalculationHashRow, CalculationRow
from .geometry import GeometryRow
from .links import StationaryIdentityLink
from .stationary import IdentityRow, StationaryPointRow


@event.listens_for(GeometryRow, "before_insert")
def populate_geometry_hash(mapper, connection, target: GeometryRow) -> None:  # noqa: ANN001, ARG001
    """Populate GeometryRow hash before inserts and updates."""
    if target.hash is None:
        target.hash = geom.geometry_hash(target)


@event.listens_for(Session, "after_flush")
def populate_calculation_hashes(session, flush_context) -> None:  # noqa: ANN001, ARG001
    """Populate the 'minimal' hash for newly added CalculationRow objects."""
    available = set(hash_registry.available())

    for row in session.new:
        if not isinstance(row, CalculationRow):
            continue

        existing = {h.name for h in row.hashes}
        missing = available - existing
        if not missing:
            continue

        calc = row

        for name in missing:
            value = calculation_hash(calc, name=name)

            session.add(
                CalculationHashRow(
                    calculation_id=row.id,
                    name=name,
                    value=value,
                )
            )


@event.listens_for(StationaryPointRow, "after_insert")
def stationary_inchi(mapper, connection, target: StationaryPointRow) -> None:  # noqa: ANN001, ARG001
    """Automatically tags InChI and default metrics after inserting StationaryPoint."""
    session = Session(bind=connection)

    if target.id is None:
        msg = f"{target = } not assigned an id."
        raise LookupError(msg)

    try:
        # NOTE: If target.geometry isn't loaded, we need to fetch it
        geom_stmt = select(GeometryRow).where(GeometryRow.id == target.geometry_id)
        geom_row = session.exec(geom_stmt).first()

        if not geom_row:
            msg = (
                f"{target.geometry_id} does not correspond to an entry in the database."
            )
            raise LookupError(msg)  # noqa: TRY301

        inchi_string = geom.inchi(geom_row)

        inchi_stmt = select(IdentityRow).where(
            IdentityRow.algorithm == "InChI", IdentityRow.value == inchi_string
        )
        id_row = session.exec(inchi_stmt).first()

        if id_row is None:
            id_row = IdentityRow(
                type="stereoisomer",
                algorithm="InChI",
                value=inchi_string,
            )
            session.add(id_row)
            session.flush()

        if id_row.id is None:
            msg = f"{id_row = } not assigned an id."
            raise LookupError(msg)  # noqa: TRY301

        link = StationaryIdentityLink(stationary_id=target.id, identity_id=id_row.id)
        session.add(link)

        session.commit()

    except Exception as e:
        session.rollback()
        msg = f"Failed to generate InChI {target.id}"
        raise RuntimeError(msg) from e
