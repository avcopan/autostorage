"""Test for database models."""

from collections.abc import Iterator

import pytest

from autostorage import Database
from autostorage.database import StationaryPointRow
from autostorage.models import CalculationRow, GeometryRow, ModelRow


@pytest.fixture
def model() -> ModelRow:
    """Fixture for ModelRow."""
    return ModelRow(
        program="ORCA",
        program_version="6.1.1",
        calc_type="test",
        method="b3lyp",
        basis="def2-SVP",
    )


@pytest.fixture
def water() -> GeometryRow:
    """Fixture for GeometryRow."""
    return GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=[[0, 0, 0], [0, 0, -1], [0, 0, 1]],  # ty:ignore[invalid-argument-type]
        charge=0,
        spin=0,
    )


@pytest.fixture
def calculation(model: ModelRow, water: GeometryRow) -> CalculationRow:
    """Fixture for CalculationRow."""
    return CalculationRow(model=model, output_geometry=water)


@pytest.fixture
def stationary_point(calculation: CalculationRow) -> StationaryPointRow:
    """Fixture for StationaryPointRow."""
    return StationaryPointRow(
        calculation=calculation,
        geometry=calculation.output_geometry,
        order=0,
        is_pseudo=False,
    )


@pytest.fixture
def database() -> Iterator[Database]:
    """In-memory database fixture."""
    db = Database(":memory:")

    try:
        yield db

    finally:
        db.close()


def test__geometry_hashing(database: Database, water: GeometryRow) -> None:
    """Test automated hashing on GeometryRow."""
    water.hash = None
    database.add(water)
    assert water.hash is not None


def test__inchi_smiles_tagging(
    database: Database, stationary_point: StationaryPointRow
) -> None:
    """Test automated inchi and smiles tags on StationaryPointRow."""
    database.add(stationary_point)

    inchi = stationary_point.identities[0]
    smiles = inchi.identity_extras[0]

    assert inchi.value == "InChI=1S/H2O/h1H2"
    assert smiles.value == "O"
