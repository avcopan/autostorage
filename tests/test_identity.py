"""Identity module tests."""

from collections.abc import Mapping

import numpy as np
import pytest
from autogeom import Geometry
from pydantic import ValidationError

from autostorage import GeometryRow
from autostorage.identity import (
    IdentityAlgorithm,
    IdentityAlgorithmRegistry,
    IdentityKind,
    hill_formula,
    rdkit_inchi,
    rdkit_smiles,
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
            other_geos: Mapping[str, Geometry] | None = None,  # noqa: ARG001
        ) -> str:
            return str(geo.atom_count)

        algorithm = IdentityAlgorithmRegistry.register(
            name="atom_count",
            kind=IdentityKind.FORMULA,
            identity_fn=atom_count_identity_fn,
            parent=rdkit_inchi,
        )
        assert IdentityAlgorithmRegistry.get("atom_count") is algorithm
        assert algorithm.parent is rdkit_inchi
        assert algorithm.identity_fn(water) == "3"

    def test_builtin_algorithms(self) -> None:
        """The built-in algorithms have the expected kinds and parents."""
        assert rdkit_inchi.kind is IdentityKind.STEREOISOMER
        assert rdkit_inchi.parent is None
        assert rdkit_smiles.kind is IdentityKind.STEREOISOMER
        assert rdkit_smiles.parent is rdkit_inchi
        assert hill_formula.kind is IdentityKind.FORMULA
        assert hill_formula.parent is rdkit_inchi


class TestIdentityAlgorithm:
    """Tests for IdentityAlgorithm."""

    def test_frozen(self) -> None:
        """Algorithms cannot be modified after registration."""
        with pytest.raises(ValidationError, match="frozen"):
            rdkit_inchi.name = "other"  # ty: ignore[invalid-assignment]

    def test_rejects_non_callable(self) -> None:
        """An identity function must be callable."""
        with pytest.raises(ValidationError):
            IdentityAlgorithm.model_validate(
                {"name": "bad", "kind": "formula", "identity_fn": "not callable"}
            )


class TestBuiltinIdentityFunctions:
    """Tests for the built-in identity functions."""

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
        assert rdkit_smiles.identity_fn(methane, other_geos) == "[H]C([H])([H])[H]"

    def test_rdkit_smiles_without_matching_other_geo(
        self, water: Geometry, methane: Geometry
    ) -> None:
        """Canonical SMILES is returned when no `other_geos` entry matches."""
        assert rdkit_smiles.identity_fn(water, other_geos={"C": methane}) == "O"

    def test_hill_formula(self, water: Geometry, methane: Geometry) -> None:
        """Formulas are in Hill order."""
        assert hill_formula.identity_fn(water) == "H2O"
        assert hill_formula.identity_fn(methane) == "CH4"

    def test_accepts_geometry_row(self, water: Geometry) -> None:
        """Identity functions accept `GeometryRow`s, including in `other_geos`."""
        row = GeometryRow(**water.model_dump())
        assert rdkit_inchi.identity_fn(row) == "InChI=1S/H2O/h1H2"
        assert rdkit_smiles.identity_fn(row, {"[H]O[H]": row}) == "[H]O[H]"
        assert np.allclose(row.coordinates, water.coordinates)
