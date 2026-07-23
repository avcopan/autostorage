"""Autostorage test fixtures."""

from collections.abc import Iterator

import numpy as np
import pytest
from numpy.random import Generator

from autostorage import (
    CalcType,
    CalculationGeometryLink,
    CalculationRow,
    Database,
    GeometryRow,
    ModelRow,
)
from autostorage.types import Role


@pytest.fixture
def rng() -> Generator:
    """Fixture for numpy rng."""
    return np.random.default_rng(seed=679)


@pytest.fixture
def database() -> Iterator[Database]:
    """In-memory database fixture."""
    db = Database(":memory:")

    try:
        yield db

    finally:
        db.close()


@pytest.fixture
def model_row() -> ModelRow:
    """Fixture for ModelRow."""
    return ModelRow(
        program="ORCA",
        program_version="6.1.1",
        method="b3lyp",
        basis="def2-SVP",
    )


@pytest.fixture
def geometry_row() -> GeometryRow:
    """Fixture for GeometryRow."""
    return GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 0.8], [0, 0, 0], [0.8, 0, 0]]),
        charge=0,
        spin=0,
    )


@pytest.fixture
def calculation_row(model_row: ModelRow) -> CalculationRow:
    """Fixture for CalculationRow."""
    return CalculationRow(model=model_row, calc_type=CalcType.UNDEFINED)


@pytest.fixture
def calc_geo_link(
    calculation_row: CalculationRow, geometry_row: GeometryRow
) -> CalculationGeometryLink:
    """Fixture for CalculationGeometryLink."""
    return CalculationGeometryLink.create(
        calculation_row, geometry_row, role=Role.INPUT
    )
