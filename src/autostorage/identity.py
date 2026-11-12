"""Identity algorithm registry with default definitions."""

from collections.abc import Mapping
from typing import ClassVar, Protocol, runtime_checkable

import autogeom
from autogeom import Geometry
from pydantic import BaseModel, ConfigDict

from .types import IdentityKind

__all__ = [
    "IdentityAlgorithm",
    "IdentityAlgorithmRegistry",
    "IdentityKind",
    "IdentityProtocol",
    "hill_formula",
    "rdkit_inchi",
    "rdkit_inchi_conn",
    "rdkit_smiles",
]

# `Mapping` is covariant in its values, so `dict[str, GeometryRow]` is accepted
type OtherGeometries = Mapping[str, Geometry] | None


@runtime_checkable
class IdentityProtocol(Protocol):
    """Protocol for identity functions."""

    def __call__(self, geo: Geometry, other_geos: OtherGeometries = None) -> str:
        """Generate the identity of `geo`, given peer geometries keyed by identity."""
        ...


class IdentityAlgorithm(BaseModel):
    """A registered identity algorithm.

    Attributes:
        name: Unique algorithm name (mirrored into `IdentityAlgorithmRow`).
        kind: Category of identity produced.
        identity_fn: ``(geo, other_geos=None) -> str``, generating the identity.
        parent: Algorithm whose identity selects the `other_geos` passed to
            `identity_fn`, if any.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    kind: IdentityKind
    identity_fn: IdentityProtocol
    parent: "IdentityAlgorithm | None" = None


class IdentityAlgorithmRegistry:
    """Central registry of all known identity algorithms."""

    algorithms: ClassVar[list[IdentityAlgorithm]] = []

    @classmethod
    def register(
        cls,
        name: str,
        kind: IdentityKind,
        identity_fn: IdentityProtocol,
        parent: IdentityAlgorithm | None = None,
    ) -> IdentityAlgorithm:
        """Create and register an identity algorithm.

        Register algorithms before opening a `Database`, which mirrors them into
        its `identity_algorithm` table.

        Args:
            name: Unique algorithm name.
            kind: Category of identity produced.
            identity_fn: Function generating the identity string of a geometry.
            parent: Algorithm whose identity selects `other_geos`. If given,
                `identity_fn` receives one geometry per existing identity value
                among the stationary points that share the parent identity.

        Raises:
            ValueError: If an algorithm named `name` is already registered.
        """
        if any(name == a.name for a in cls.algorithms):
            msg = f"Identity algorithm {name!r} is already registered."
            raise ValueError(msg)
        algorithm = IdentityAlgorithm(
            name=name, kind=kind, identity_fn=identity_fn, parent=parent
        )
        cls.algorithms.append(algorithm)
        return algorithm

    @classmethod
    def get(cls, name: str) -> IdentityAlgorithm:
        """Get a registered identity algorithm by name.

        Raises:
            KeyError: If no algorithm named `name` is registered.
        """
        try:
            return next(a for a in cls.algorithms if a.name == name)
        except StopIteration:
            available = ", ".join(sorted(a.name for a in cls.algorithms))
            msg = f"Unknown identity algorithm {name!r}. Available: {available}"
            raise KeyError(msg) from None


def rdkit_inchi_conn_identity_fn(
    geo: Geometry,
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> str:
    """Generate a connectivity InChI string with RDKit."""
    return autogeom.inchi(geo, stereo=False)


rdkit_inchi_conn = IdentityAlgorithmRegistry.register(
    name="rdkit_inchi_conn",
    kind=IdentityKind.ISOMER,
    identity_fn=rdkit_inchi_conn_identity_fn,
)
"""Connectivity InChI from RDKit (kind: isomer)."""


def rdkit_inchi_identity_fn(
    geo: Geometry,
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> str:
    """Generate a standard InChI string with RDKit."""
    return autogeom.inchi(geo)


rdkit_inchi = IdentityAlgorithmRegistry.register(
    name="rdkit_inchi",
    kind=IdentityKind.STEREOISOMER,
    identity_fn=rdkit_inchi_identity_fn,
)
"""Standard InChI from RDKit (kind: stereoisomer)."""


def rdkit_smiles_identity_fn(geo: Geometry, other_geos: OtherGeometries = None) -> str:
    """Generate a SMILES string with RDKit.

    If a geometry in `other_geos` has the same InChI, its SMILES key is returned,
    so that equivalent species share one (possibly non-canonical) SMILES.
    Otherwise, RDKit's canonical SMILES is returned.
    """
    if other_geos:
        inchi = autogeom.inchi(geo)
        for smiles, other_geo in other_geos.items():
            if autogeom.inchi(other_geo) == inchi:
                return smiles
    return autogeom.smiles(geo)


rdkit_smiles = IdentityAlgorithmRegistry.register(
    name="rdkit_smiles",
    kind=IdentityKind.STEREOISOMER,
    identity_fn=rdkit_smiles_identity_fn,
    parent=rdkit_inchi,
)
"""SMILES from RDKit (kind: stereoisomer; parent: `rdkit_inchi`).

The SMILES of an existing stationary point with the same InChI is reused.
"""


def hill_formula_identity_fn(
    geo: Geometry,
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> str:
    """Generate the molecular formula in Hill order."""
    return autogeom.formula(geo)


hill_formula = IdentityAlgorithmRegistry.register(
    name="hill_formula",
    kind=IdentityKind.FORMULA,
    identity_fn=hill_formula_identity_fn,
    parent=rdkit_inchi,
)
"""Molecular formula in Hill order (kind: formula; parent: `rdkit_inchi`)."""
