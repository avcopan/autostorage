"""Identity module tests."""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError

import numpy as np
import protomol
import pytest
from autogeom import Geometry
from protomol import AnyGraph

from autostorage import GeometryRow
from autostorage.identity import (
    SADDLE_ORDERS,
    IdentityAlgorithm,
    IdentityAlgorithmRegistry,
    IdentityKind,
    IdentityResult,
    hill_formula,
    protomol_graph,
    rdkit_inchi,
    rdkit_inchi_conn,
    rdkit_smiles,
    smg_conn,
)


def _geometry(symbols: list[str], coordinates: list[list[float]]) -> Geometry:
    """Build a closed-shell neutral geometry."""
    return Geometry(symbols=symbols, coordinates=coordinates, charge=0, spin=0)


@pytest.fixture
def water() -> Geometry:
    """Water geometry."""
    return _geometry(["O", "H", "H"], [[0, 0, 0], [0, 0, 0.96], [0.93, 0, -0.24]])


@pytest.fixture
def methane() -> Geometry:
    """Methane geometry."""
    r = 0.63
    return _geometry(
        ["C", "H", "H", "H", "H"],
        [[0, 0, 0], [r, r, r], [r, -r, -r], [-r, r, -r], [-r, -r, r]],
    )


@pytest.fixture
def cis_difluoroethene() -> Geometry:
    """Planar cis-1,2-difluoroethene sketch (C2H2F2)."""
    return _geometry(
        ["C", "C", "F", "H", "F", "H"],
        [
            [-0.6, 0, 0],
            [0.6, 0, 0],
            [-1.2, 1, 0],
            [-1.2, -1, 0],
            [1.2, 1, 0],
            [1.2, -1, 0],
        ],
    )


@pytest.fixture
def trans_difluoroethene() -> Geometry:
    """Planar trans-1,2-difluoroethene sketch (C2H2F2)."""
    return _geometry(
        ["C", "C", "F", "H", "F", "H"],
        [
            [-0.6, 0, 0],
            [0.6, 0, 0],
            [-1.2, 1, 0],
            [-1.2, -1, 0],
            [1.2, -1, 0],
            [1.2, 1, 0],
        ],
    )


class TestIdentityAlgorithmRegistry:
    """Tests for IdentityAlgorithmRegistry."""

    def test_get(self) -> None:
        """A registered algorithm is returned by name."""
        assert IdentityAlgorithmRegistry.get("rdkit_inchi") is rdkit_inchi

    def test_get_unknown(self) -> None:
        """Looking up an unregistered name raises a KeyError listing the options."""
        with pytest.raises(KeyError, match=r"Unknown identity algorithm 'nope'.*rdk"):
            IdentityAlgorithmRegistry.get("nope")

    def test_register_duplicate(self) -> None:
        """Registering an existing name raises a ValueError."""
        with pytest.raises(ValueError, match="already registered"):
            IdentityAlgorithmRegistry.register(
                name="rdkit_inchi",
                kind=IdentityKind.STEREOISOMER,
                identity_fn=rdkit_inchi.identity_fn,
            )

    def test_register_custom(
        self, monkeypatch: pytest.MonkeyPatch, water: Geometry
    ) -> None:
        """A user-defined algorithm with a parent can be registered and looked up."""
        # Register into a copy, so that other tests don't see this algorithm
        monkeypatch.setattr(
            IdentityAlgorithmRegistry,
            "algorithms",
            list(IdentityAlgorithmRegistry.algorithms),
        )

        def atom_count_identity_fn(
            geo: Geometry,
            gra: AnyGraph | None = None,  # noqa: ARG001
            other_geos: Mapping[str, Geometry] | None = None,  # noqa: ARG001
        ) -> str:
            return str(geo.atom_count)

        # Order restriction must be compatible with parent
        #  => This raises an error:
        with pytest.raises(ValueError, match="not compatible"):
            algorithm = IdentityAlgorithmRegistry.register(
                name="atom_count",
                kind=IdentityKind.FORMULA,
                identity_fn=atom_count_identity_fn,
                parent=rdkit_inchi,
            )
        #  => This does not:
        algorithm = IdentityAlgorithmRegistry.register(
            name="atom_count",
            kind=IdentityKind.FORMULA,
            identity_fn=atom_count_identity_fn,
            parent=rdkit_inchi,
            orders={0},
        )
        assert IdentityAlgorithmRegistry.get("atom_count") is algorithm
        assert algorithm.parent is rdkit_inchi
        assert algorithm.identity_fn(water) == "3"
        assert not algorithm.uses_graph

    def test_register_graph_algorithm(
        self, monkeypatch: pytest.MonkeyPatch, water: Geometry
    ) -> None:
        """An algorithm that reads the graph is registered with `uses_graph=True`."""
        monkeypatch.setattr(
            IdentityAlgorithmRegistry,
            "algorithms",
            list(IdentityAlgorithmRegistry.algorithms),
        )

        def graph_identity_fn(
            geo: Geometry,  # noqa: ARG001
            gra: AnyGraph | None = None,
            other_geos: Mapping[str, Geometry] | None = None,  # noqa: ARG001
        ) -> str:
            assert isinstance(gra, protomol.StereoMolGraph)
            return protomol.canonical_json(gra)

        algorithm = IdentityAlgorithmRegistry.register(
            name="graph",
            kind=IdentityKind.GRAPH,
            identity_fn=graph_identity_fn,
            uses_graph=True,
        )
        gra = protomol.from_geometry(water)
        assert algorithm.uses_graph
        assert algorithm.identity_fn(water, gra) == protomol.canonical_json(gra)

    def test_builtin_algorithms(self) -> None:
        """The built-in algorithms have the expected kinds and parents."""
        assert rdkit_inchi_conn.kind is IdentityKind.ISOMER
        assert rdkit_inchi_conn.parent is None
        assert rdkit_inchi_conn.orders == {0}
        assert rdkit_inchi.kind is IdentityKind.STEREOISOMER
        assert rdkit_inchi.parent is None
        assert rdkit_inchi.orders == {0}
        assert rdkit_smiles.kind is IdentityKind.STEREOISOMER
        assert rdkit_smiles.parent is rdkit_inchi
        assert rdkit_smiles.orders == {0}
        assert hill_formula.kind is IdentityKind.FORMULA
        assert hill_formula.parent is None
        assert hill_formula.orders is None
        builtins = (rdkit_inchi_conn, rdkit_inchi, rdkit_smiles, hill_formula)
        assert not any(alg.uses_graph for alg in builtins)
        assert protomol_graph.kind is IdentityKind.GRAPH
        assert protomol_graph.orders == SADDLE_ORDERS
        assert 0 not in SADDLE_ORDERS
        assert protomol_graph.uses_graph
        assert protomol_graph.stores_graph

    def test_stores_graph_implies_uses_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`register(stores_graph=True)` sets `uses_graph`; the dataclass checks it."""
        monkeypatch.setattr(
            IdentityAlgorithmRegistry,
            "algorithms",
            list(IdentityAlgorithmRegistry.algorithms),
        )
        algorithm = IdentityAlgorithmRegistry.register(
            name="graph_copy",
            kind=IdentityKind.GRAPH,
            identity_fn=protomol_graph.identity_fn,
            stores_graph=True,
        )
        assert algorithm.uses_graph
        with pytest.raises(ValueError, match="must use one"):
            IdentityAlgorithm(
                name="bad",
                kind=IdentityKind.GRAPH,
                identity_fn=protomol_graph.identity_fn,
                stores_graph=True,
            )

    def test_builtins_ignore_graph(self, water: Geometry) -> None:
        """The built-in identity functions give the same value with a graph."""
        gra = protomol.from_geometry(water)
        for alg in (rdkit_inchi_conn, rdkit_inchi, rdkit_smiles, hill_formula):
            assert alg.identity_fn(water, gra) == alg.identity_fn(water)


class TestIdentityAlgorithm:
    """Tests for IdentityAlgorithm."""

    def test_frozen(self) -> None:
        """Algorithms cannot be modified after registration."""
        with pytest.raises(FrozenInstanceError):
            rdkit_inchi.name = "other"  # ty: ignore[invalid-assignment]

    def test_rejects_non_callable(self) -> None:
        """An identity function must be callable."""
        with pytest.raises(TypeError, match="not callable"):
            IdentityAlgorithm(
                name="bad",
                kind=IdentityKind.FORMULA,
                identity_fn="not callable",  # ty: ignore[invalid-argument-type]
            )


class TestBuiltinIdentityFunctions:
    """Tests for the built-in identity functions."""

    def test_rdkit_inchi_conn(self, water: Geometry, methane: Geometry) -> None:
        """Connectivity InChI is generated from a geometry."""
        assert rdkit_inchi_conn.identity_fn(water) == "InChI=1S/H2O/h1H2"
        assert rdkit_inchi_conn.identity_fn(methane) == "InChI=1S/CH4/h1H4"

    def test_rdkit_inchi_conn_ignores_stereo(
        self, cis_difluoroethene: Geometry, trans_difluoroethene: Geometry
    ) -> None:
        """Stereoisomers share a connectivity InChI but not a standard InChI."""
        conn = "InChI=1S/C2H2F2/c3-1-2-4/h1-2H"
        assert rdkit_inchi_conn.identity_fn(cis_difluoroethene) == conn
        assert rdkit_inchi_conn.identity_fn(trans_difluoroethene) == conn
        assert rdkit_inchi.identity_fn(cis_difluoroethene) == f"{conn}/b2-1-"
        assert rdkit_inchi.identity_fn(trans_difluoroethene) == f"{conn}/b2-1+"

    def test_rdkit_inchi(self, water: Geometry) -> None:
        """InChI is generated from a geometry."""
        assert rdkit_inchi.identity_fn(water) == "InChI=1S/H2O/h1H2"

    def test_rdkit_smiles(self, water: Geometry) -> None:
        """Canonical SMILES is generated from a geometry."""
        assert rdkit_smiles.identity_fn(water) == "O"

    def test_rdkit_smiles_reuses_matching_other_geo(self, methane: Geometry) -> None:
        """The SMILES key of an `other_geos` entry with the same InChI is reused."""
        other_geos = {"[H]C([H])([H])[H]": methane.model_copy(deep=True)}
        assert rdkit_smiles.identity_fn(methane) == "C"
        assert (
            rdkit_smiles.identity_fn(methane, None, other_geos) == "[H]C([H])([H])[H]"
        )

    def test_rdkit_smiles_without_matching_other_geo(
        self, water: Geometry, methane: Geometry
    ) -> None:
        """Canonical SMILES is returned when no `other_geos` entry matches."""
        assert rdkit_smiles.identity_fn(water, other_geos={"C": methane}) == "O"

    def test_hill_formula(self, water: Geometry, methane: Geometry) -> None:
        """Formulas are in Hill order."""
        assert hill_formula.identity_fn(water) == "H2O"
        assert hill_formula.identity_fn(methane) == "CH4"

    def test_protomol_graph(self, water: Geometry) -> None:
        """The canonical graph's JSON, and the map back to the given graph."""
        gra = protomol.from_geometry(water)
        result = protomol_graph.identity_fn(water, gra)
        assert isinstance(result, IdentityResult)
        assert result.value == protomol.canonical_json(gra)
        assert result.atom_map is not None
        canonical = protomol.from_json(result.value)
        inverse = np.argsort(result.atom_map).tolist()
        assert protomol.relabel(canonical, inverse) == gra  # ty: ignore[invalid-argument-type]

    def test_protomol_graph_needs_graph(self, water: Geometry) -> None:
        """Without a graph, `protomol_graph@0` raises a ValueError."""
        with pytest.raises(ValueError, match="needs a graph"):
            protomol_graph.identity_fn(water)

    def test_smg_conn_properties(self) -> None:
        """`smg_conn@1` is an isomer, for minima and TSs, graph-reading, non-storing."""
        assert smg_conn.name == "smg_conn@1"
        assert smg_conn.kind is IdentityKind.ISOMER
        assert smg_conn.orders == {0, 1}
        assert smg_conn.uses_graph
        assert not smg_conn.stores_graph

    def test_smg_conn_ignores_stereo(
        self, cis_difluoroethene: Geometry, trans_difluoroethene: Geometry
    ) -> None:
        """Stereoisomers share `smg_conn@1` but not the InChI."""
        cis_gra = protomol.from_geometry(cis_difluoroethene)
        trans_gra = protomol.from_geometry(trans_difluoroethene)
        assert cis_gra != trans_gra
        cis = smg_conn.identity_fn(cis_difluoroethene, cis_gra)
        trans = smg_conn.identity_fn(trans_difluoroethene, trans_gra)
        assert isinstance(cis, IdentityResult)
        assert isinstance(trans, IdentityResult)
        assert cis.value == trans.value
        assert cis.value == protomol.canonical_json(protomol.without_stereo(cis_gra))
        assert rdkit_inchi.identity_fn(cis_difluoroethene) != rdkit_inchi.identity_fn(
            trans_difluoroethene
        )

    def test_smg_conn_relabelled(self, cis_difluoroethene: Geometry) -> None:
        """A relabelled geometry gives the same value, with its own atom map."""
        perm = [3, 5, 0, 4, 1, 2]
        geo = cis_difluoroethene
        relabelled = _geometry(
            [geo.symbols[i] for i in perm], [geo.coordinates[i].tolist() for i in perm]
        )
        a = smg_conn.identity_fn(geo, protomol.from_geometry(geo))
        b = smg_conn.identity_fn(relabelled, protomol.from_geometry(relabelled))
        assert isinstance(a, IdentityResult)
        assert isinstance(b, IdentityResult)
        assert a.value == b.value
        assert a.atom_map != b.atom_map

    def test_smg_conn_plain_graph(self, water: Geometry) -> None:
        """A graph without stereo fields is used as it is."""
        gra = protomol.without_stereo(protomol.from_geometry(water))
        result = smg_conn.identity_fn(water, gra)
        assert isinstance(result, IdentityResult)
        assert result.value == protomol.canonical_json(gra)

    def test_ts_graph_and_reverse_share_value(self, water: Geometry) -> None:
        """A TS graph and its reverse give one value, for both TS-capable algorithms."""
        ts_gra = protomol.examples.abstraction_ts()
        rev = protomol.reverse(ts_gra)
        assert rev != ts_gra
        for alg in (smg_conn, protomol_graph):
            a = alg.identity_fn(water, ts_gra)
            b = alg.identity_fn(water, rev)
            assert isinstance(a, IdentityResult)
            assert isinstance(b, IdentityResult)
            assert a.value == b.value
            assert a.cache is not None
            assert b.cache is not None
            assert a.cache["reversed"] != b.cache["reversed"]
            # The atom map takes the canonical graph to the (maybe reversed) graph
            canonical = protomol.from_json(a.value)
            assert a.atom_map is not None
            back = protomol.relabel(canonical, np.argsort(a.atom_map).tolist())  # ty: ignore[invalid-argument-type]
            expected = protomol.reverse(ts_gra) if a.cache["reversed"] else ts_gra
            if alg is protomol_graph:
                assert back == expected
            else:
                assert back == protomol.without_stereo(expected)

    def test_minimum_graph_has_no_reversal_cache(self, water: Geometry) -> None:
        """A minimum's graph has no direction, so no `reversed` entry."""
        result = smg_conn.identity_fn(water, protomol.from_geometry(water))
        assert isinstance(result, IdentityResult)
        assert result.cache is None

    def test_smg_conn_needs_graph(self, water: Geometry) -> None:
        """Without a graph, `smg_conn@1` raises a ValueError."""
        with pytest.raises(ValueError, match="needs a graph"):
            smg_conn.identity_fn(water)

    def test_accepts_geometry_row(self, water: Geometry) -> None:
        """Identity functions accept `GeometryRow`s, including in `other_geos`."""
        row = GeometryRow(**water.model_dump())
        assert rdkit_inchi.identity_fn(row) == "InChI=1S/H2O/h1H2"
        assert rdkit_inchi_conn.identity_fn(row) == "InChI=1S/H2O/h1H2"
        assert rdkit_smiles.identity_fn(row, None, {"[H]O[H]": row}) == "[H]O[H]"
        assert np.allclose(row.coordinates, water.coordinates)
