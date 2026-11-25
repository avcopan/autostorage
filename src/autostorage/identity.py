"""Identity algorithm registry with default definitions."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

import autogeom
import protomol
from autogeom import Geometry
from protomol import AnyGraph
from protomol._geometry import _with_parities_from_geometry

from .types import IdentityKind

__all__ = [
    "IdentityAlgorithm",
    "IdentityAlgorithmRegistry",
    "IdentityKind",
    "IdentityProtocol",
    "IdentityResult",
    "hill_formula",
    "protomol_graph",
    "rdkit_inchi",
    "rdkit_inchi_conn",
    "rdkit_smiles",
    "smg_conn",
    "smg_low_t",
]

SADDLE_ORDERS = frozenset(range(1, 10))
"""The orders of saddle points (`order >= 1`), for algorithms that apply to them."""

# `Mapping` is covariant in its values, so `dict[str, GeometryRow]` is accepted
type OtherGeometries = Mapping[str, Geometry] | None


@dataclass(frozen=True)
class IdentityResult:
    """An identity value with per-point data, returned by an identity function.

    Attributes:
        value: The identity value.
        atom_map: ``atom_map[k]`` is the geometry index of canonical atom ``k``, for
            an identity built from a canonical form. Stored on the point's link
            and checked on flush to be a permutation of the geometry's atoms.
        cache: Algorithm-specific data, stored in the link's `algorithm_cache`.
    """

    value: str
    atom_map: Sequence[int] | None = None
    cache: dict[str, Any] | None = None


@runtime_checkable
class IdentityProtocol(Protocol):
    """Protocol for identity functions."""

    def __call__(
        self,
        geo: Geometry,
        gra: AnyGraph | None = None,
        other_geos: OtherGeometries = None,
    ) -> str | IdentityResult:
        """Generate the identity of `geo`, given its graph and peer geometries.

        `gra` is the protomol graph of `geo`, index-aligned with it, or `None`.
        `other_geos` holds peer geometries keyed by their identity value. Return
        the value, or an `IdentityResult` to also store an atom map or a cache.
        """
        ...


@dataclass(frozen=True)
class IdentityAlgorithm:
    """A registered identity algorithm.

    Attributes:
        name: Unique algorithm name (mirrored into `IdentityAlgorithmRow`).
        kind: Category of identity produced.
        identity_fn: ``(geo, gra=None, other_geos=None) -> str | IdentityResult``,
            generating the identity.
        parent: Algorithm whose identity selects the `other_geos` passed to
            `identity_fn`, if any.
        orders: Stationary point orders the algorithm applies to. `None` if it
            applies to any order.
        uses_graph: Whether `identity_fn` reads `gra`. Such an algorithm is passed
            the point's graph, perceived from the geometry for a minimum, and is
            skipped for a saddle point without one.
        stores_graph: Whether the value is the canonical graph (`protomol.to_json`)
            and the result's `atom_map` maps it to the geometry, so that the
            point's graph can be rebuilt from the link. Implies `uses_graph`.
    """

    name: str
    kind: IdentityKind
    identity_fn: IdentityProtocol
    parent: "IdentityAlgorithm | None" = None
    orders: frozenset[int] | None = None
    uses_graph: bool = False
    stores_graph: bool = False

    def applies_to(self, order: int) -> bool:
        """Check whether algorithm applies to a given order."""
        return self.orders is None or order in self.orders

    def __post_init__(self) -> None:
        """Check the function and that the orders are a subset of the parent's.

        Raises:
            TypeError: If `identity_fn` isn't callable.
            ValueError: If the orders aren't a subset of the parent's orders, or
                `stores_graph` is set without `uses_graph`.
        """
        if not callable(self.identity_fn):
            msg = f"Identity function of {self.name!r} is not callable."
            raise TypeError(msg)

        if self.stores_graph and not self.uses_graph:
            msg = (
                f"Identity algorithm {self.name!r} stores a graph, so it must use one."
            )
            raise ValueError(msg)

        if self.parent is None or self.parent.orders is None:
            return

        if self.orders is None or not self.orders <= self.parent.orders:
            child = "all" if self.orders is None else sorted(self.orders)
            parent = sorted(self.parent.orders)
            msg = (
                f"Orders {child} for child identity algorithm {self.name} "
                f"are not compatible with orders {parent} or parent identity "
                f"algorithm {self.parent.name}."
            )
            raise ValueError(msg)


class IdentityAlgorithmRegistry:
    """Central registry of all known identity algorithms."""

    algorithms: ClassVar[list[IdentityAlgorithm]] = []

    @classmethod
    def register(  # noqa: PLR0913
        cls,
        name: str,
        kind: IdentityKind,
        identity_fn: IdentityProtocol,
        *,
        parent: IdentityAlgorithm | None = None,
        orders: Iterable[int] | None = None,
        uses_graph: bool = False,
        stores_graph: bool = False,
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
            orders: Stationary point orders the algorithm applies to. `None` if it
                applies to any order.
            uses_graph: Whether `identity_fn` reads its `gra` argument. Graphs are
                only perceived for points that such an algorithm applies to.
            stores_graph: Whether `identity_fn` returns an `IdentityResult` whose
                value is the canonical graph's JSON and whose `atom_map` maps it to
                the geometry. The point's `graph` is read back from such a link.
                Sets `uses_graph`.

        Raises:
            ValueError: If an algorithm named `name` is already registered, or
                `orders` isn't a subset of the parent's orders.
        """
        if any(name == a.name for a in cls.algorithms):
            msg = f"Identity algorithm {name!r} is already registered."
            raise ValueError(msg)
        orders = None if orders is None else frozenset(orders)
        algorithm = IdentityAlgorithm(
            name=name,
            kind=kind,
            identity_fn=identity_fn,
            parent=parent,
            orders=orders,
            uses_graph=uses_graph or stores_graph,
            stores_graph=stores_graph,
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
    gra: AnyGraph | None = None,  # noqa: ARG001
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> str:
    """Generate a connectivity InChI string with RDKit."""
    return autogeom.inchi(geo, stereo=False)


rdkit_inchi_conn = IdentityAlgorithmRegistry.register(
    name="rdkit_inchi_conn",
    kind=IdentityKind.ISOMER,
    identity_fn=rdkit_inchi_conn_identity_fn,
    orders={0},
)
"""Connectivity InChI from RDKit (kind: isomer; minima only)."""


def rdkit_inchi_identity_fn(
    geo: Geometry,
    gra: AnyGraph | None = None,  # noqa: ARG001
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> str:
    """Generate a standard InChI string with RDKit."""
    return autogeom.inchi(geo)


rdkit_inchi = IdentityAlgorithmRegistry.register(
    name="rdkit_inchi",
    kind=IdentityKind.STEREOISOMER,
    identity_fn=rdkit_inchi_identity_fn,
    orders={0},
)
"""Standard InChI from RDKit (kind: stereoisomer; minima only)."""


def rdkit_smiles_identity_fn(
    geo: Geometry,
    gra: AnyGraph | None = None,  # noqa: ARG001
    other_geos: OtherGeometries = None,
) -> str:
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
    orders={0},
)
"""SMILES from RDKit (kind: stereoisomer; parent: `rdkit_inchi`; minima only).

The SMILES of an existing stationary point with the same InChI is reused.
"""


def hill_formula_identity_fn(
    geo: Geometry,
    gra: AnyGraph | None = None,  # noqa: ARG001
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> str:
    """Generate the molecular formula in Hill order."""
    return autogeom.formula(geo)


hill_formula = IdentityAlgorithmRegistry.register(
    name="hill_formula",
    kind=IdentityKind.FORMULA,
    identity_fn=hill_formula_identity_fn,
)
"""Molecular formula in Hill order (kind: formula)."""


def _is_reaction(gra: AnyGraph) -> bool:
    """Whether `gra` is a reaction graph (a TS graph)."""
    return isinstance(gra, protomol.ReactionGraph | protomol.StereoReactionGraph)


def _graph_result(gra: AnyGraph) -> IdentityResult:
    """The canonical JSON of `gra` in its canonical direction, with its atom map."""
    reverse = False
    if _is_reaction(gra):
        gra, reverse = protomol.canonical_direction(gra)  # ty: ignore[invalid-argument-type]
    canonical, atom_map = protomol.canonical_form(gra)  # ty: ignore[invalid-argument-type]
    cache = {"reversed": reverse} if _is_reaction(gra) else None
    return IdentityResult(protomol.to_json(canonical), atom_map=atom_map, cache=cache)


def protomol_graph_identity_fn(
    geo: Geometry,  # noqa: ARG001
    gra: AnyGraph | None = None,
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> IdentityResult:
    """The canonical graph's JSON, with the atom map from it to the geometry.

    A reaction graph is put in its canonical direction first (see
    `protomol.canonical_direction`), and `algorithm_cache["reversed"]` says whether
    it was reversed.

    Raises:
        ValueError: If no graph is given.
    """
    if gra is None:
        msg = "protomol_graph@0 needs a graph."
        raise ValueError(msg)
    return _graph_result(gra)


protomol_graph = IdentityAlgorithmRegistry.register(
    name="protomol_graph@0",
    kind=IdentityKind.GRAPH,
    identity_fn=protomol_graph_identity_fn,
    orders=SADDLE_ORDERS,
    stores_graph=True,
)
"""The protomol graph as given, canonicalized (kind: graph; saddle points only;
stores the graph).

Interim durable graph of a transition state, until TS sites exist (pm P57); a
minimum gets its stored graph from `smg_low_t@1`. A reaction graph is put in its
canonical direction, so a TS and its reverse share one value; a saddle point needs
its reaction graph.
"""


def smg_conn_identity_fn(
    geo: Geometry,  # noqa: ARG001
    gra: AnyGraph | None = None,
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> IdentityResult:
    """The canonical JSON of the stereo-free graph, with the atom map to the geometry.

    A reaction graph is put in its canonical direction (of the stereo-free graph),
    and `algorithm_cache["reversed"]` says whether it was reversed.

    Raises:
        ValueError: If no graph is given.
    """
    if gra is None:
        msg = "smg_conn@1 needs a graph."
        raise ValueError(msg)
    if isinstance(gra, protomol.StereoMolGraph | protomol.StereoReactionGraph):
        gra = protomol.without_stereo(gra)
    return _graph_result(gra)


smg_conn = IdentityAlgorithmRegistry.register(
    name="smg_conn@1",
    kind=IdentityKind.ISOMER,
    identity_fn=smg_conn_identity_fn,
    orders={0, 1},
    uses_graph=True,
)
"""Stereo-free canonical graph (kind: isomer; minima and first-order saddle points).

It does not store the graph (`stores_graph=False`): the stored graph would be
stereo-free, and `IdentityKind.graph_preference` ranks `isomer` above `graph`, so it
would displace the stereo-aware graph (`smg_low_t@1` for a minimum, the interim
`protomol_graph@0` for a TS) as the one a point reads and passes to its `uses_graph`
algorithms. A reaction graph is put in its canonical direction first.
"""


def smg_low_t_identity_fn(
    geo: Geometry,
    gra: AnyGraph | None = None,
    other_geos: OtherGeometries = None,  # noqa: ARG001
) -> IdentityResult:
    """The canonical graph under the low-T scheme, with the atom map to the geometry.

    The graph's sites are reassigned by `protomol.low_t` (pm P54, P57): a site the
    graph has keeps its parity, and a site the scheme adds gets its parity from the
    geometry (pm P53), or stays undetermined where the coordinates don't decide it.

    Raises:
        ValueError: If no graph is given, or it is a reaction graph.
    """
    if gra is None:
        msg = "smg_low_t@1 needs a graph."
        raise ValueError(msg)
    if not isinstance(gra, protomol.MolGraph | protomol.StereoMolGraph):
        msg = "smg_low_t@1 takes a species graph, not a reaction graph."
        raise ValueError(msg)  # noqa: TRY004  (an IdentityGenerationWarning)
    return _graph_result(_with_parities_from_geometry(protomol.low_t(gra), geo))


smg_low_t = IdentityAlgorithmRegistry.register(
    name="smg_low_t@1",
    kind=IdentityKind.LOW_T_STEREOISOMER,
    identity_fn=smg_low_t_identity_fn,
    orders={0},
    stores_graph=True,
)
"""Canonical graph under the low-T scheme (kind: low_t_stereoisomer; minima only;
stores the graph).

The stored graph of a minimum, and the one its `uses_graph` algorithms are passed
on regeneration (`IdentityKind.graph_preference` ranks `low_t_stereoisomer` first).
Unlike `rdkit_inchi`, it tells apart configurations that only interconvert at high
temperature, such as the two invertomers of an amine N.
"""
