"""Query statement factories for the AutoStorage schema."""

from sqlmodel import col, select
from sqlmodel.sql.expression import SelectOfScalar

from .identity import IdentityAlgorithm
from .models import (
    IdentityAlgorithmRow,
    IdentityRow,
    IdentityStationaryLink,
    StationaryPointRow,
)

__all__ = ["stationary_point_by_identity"]


def stationary_point_by_identity(
    algorithm: IdentityAlgorithm | IdentityAlgorithmRow | str,
    value: str,
    *,
    include_pseudo: bool = False,
) -> SelectOfScalar[StationaryPointRow]:
    """Select stationary points with a given identity.

    Args:
        algorithm: Identity algorithm, e.g. `autostorage.rdkit_inchi`, an
            `IdentityAlgorithmRow`, or an algorithm name.
        value: Identity value, e.g. an InChI string.
        include_pseudo: Whether to also select pseudo stationary points.

    Returns:
        Statement to run with `session.exec(...)`.
    """
    name = algorithm if isinstance(algorithm, str) else algorithm.name
    stmt = (
        select(StationaryPointRow)
        .join(
            target=IdentityStationaryLink,
            onclause=col(IdentityStationaryLink.stationary_id)
            == col(StationaryPointRow.id),
        )
        .join(
            target=IdentityRow,
            onclause=col(IdentityRow.id) == col(IdentityStationaryLink.identity_id),
        )
        .join(
            target=IdentityAlgorithmRow,
            onclause=col(IdentityAlgorithmRow.id) == col(IdentityRow.algorithm_id),
        )
        .where(
            col(IdentityRow.value) == value,
            col(IdentityAlgorithmRow.name) == name,
        )
    )
    if not include_pseudo:
        stmt = stmt.where(col(StationaryPointRow.is_pseudo).is_(False))
    return stmt
