"""Query statement factories for the AutoStorage schema."""

from sqlmodel import col, select
from sqlmodel.sql.expression import SelectOfScalar

from .identity import IdentityAlgorithm
from .model_hash import ModelHashAlgorithm
from .models import (
    IdentityAlgorithmRow,
    IdentityRow,
    IdentityStationaryLink,
    ModelHashAlgorithmRow,
    ModelHashLink,
    ModelHashRow,
    ModelRow,
    StationaryPointRow,
)

__all__ = ["model_by_hash", "stationary_point_by_identity"]


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
        .where(
            col(IdentityRow.value) == value,
            col(IdentityRow.algorithm_name) == name,
        )
    )
    if not include_pseudo:
        stmt = stmt.where(col(StationaryPointRow.is_pseudo).is_(False))
    return stmt


def model_by_hash(
    algorithm: ModelHashAlgorithm | ModelHashAlgorithmRow | str,
    value: str,
) -> SelectOfScalar[ModelRow]:
    """Select models with a given hash value.

    Args:
        algorithm: Model hash algorithm, e.g. `autostorage.minimal_hash`, a
            `ModelHashAlgorithmRow`, or an algorithm name.
        value: Hash value, e.g. ``"b3lyp/6-31g*"``.

    Returns:
        Statement to run with `session.exec(...)`.
    """
    name = algorithm if isinstance(algorithm, str) else algorithm.name
    return (
        select(ModelRow)
        .join(
            target=ModelHashLink,
            onclause=col(ModelHashLink.model_id) == col(ModelRow.id),
        )
        .join(
            target=ModelHashRow,
            onclause=col(ModelHashRow.id) == col(ModelHashLink.hash_id),
        )
        .where(
            col(ModelHashRow.value) == value,
            col(ModelHashRow.algorithm_name) == name,
        )
    )
