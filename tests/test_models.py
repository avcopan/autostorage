"""Test for database models."""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from autostorage import Database
from autostorage.database import (
    CalculationRow,
    GeometryRow,
    GradientRow,
    HessianRow,
    ModelRow,
    StationaryPointRow,
)

DATA_PATH = Path(__file__).parent / "data"


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
def propyl_geometry() -> GeometryRow:
    """Fixture for propyl oxirane geometry."""
    return GeometryRow.from_xyz_file(DATA_PATH / "propyl_oxirane.xyz", charge=0, spin=1)


@pytest.fixture
def propyl_calculation(propyl_geometry: GeometryRow) -> CalculationRow:
    """Fixture for mock Hessian calculation."""
    hessian_model = ModelRow(
        program="foo",
        method="bar",
        calc_type="hessian",
    )
    return CalculationRow(model=hessian_model, input_geometry=propyl_geometry)


@pytest.fixture
def propyl_hessian(propyl_calculation: CalculationRow) -> HessianRow:
    """Fixture for propyl oxirane hessian."""
    return HessianRow(
        geometry=propyl_calculation.input_geometry,
        calculation=propyl_calculation,
        value=np.loadtxt(DATA_PATH / "propyl_oxirane_hessian.gz").tolist(),
    )


@pytest.fixture
def propyl_stationary(propyl_hessian: HessianRow) -> StationaryPointRow:
    """Fixture for propyl oxirane stationary point."""
    return StationaryPointRow(
        geometry=propyl_hessian.geometry,
        calculation=propyl_hessian.calculation,
        hessian=propyl_hessian,
        order=0,
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


def test__valid_gradient_shape(
    database: Database, propyl_calculation: CalculationRow
) -> None:
    """Test that the Hessian shape is validated."""
    grad = GradientRow(
        geometry=propyl_calculation.input_geometry,
        calculation=propyl_calculation,
        value=[1, 1, 1],
    )

    with pytest.raises(ValueError):  # noqa: PT011
        database.add(grad)


def test__valid_hessian_shape(
    database: Database, propyl_calculation: CalculationRow
) -> None:
    """Test that the Hessian shape is validated."""
    hess = HessianRow(
        geometry=propyl_calculation.input_geometry,
        calculation=propyl_calculation,
        value=[[1, 1, 1]],
    )

    with pytest.raises(ValueError):  # noqa: PT011
        database.add(hess)


def test__stationary_order_validation(
    database: Database, propyl_stationary: StationaryPointRow
) -> None:
    """Test stationary point order validation by Hessian evaluation."""
    database.add(propyl_stationary)

    assert propyl_stationary.is_valid
