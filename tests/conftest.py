"""Fixtures for tests."""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from automatics import Calculation, Geometry

from autostorage import Database
from autostorage.models import CalculationRow, GeometryRow

DATA_PATH = Path(__file__).parent / "data"


@pytest.fixture
def calc() -> Calculation:
    """Fixture for sample Calculation."""
    return Calculation(
        program="psi4",
        program_keywords={"dft_functional": "b3lyp", "scf_type": "df"},
        method="b3lyp",
        calc_type="energy",
    )


@pytest.fixture
def calc_row() -> Calculation:
    """Fixture for sample Calculation."""
    return CalculationRow(
        program="psi4",
        program_keywords={"dft_functional": "b3lyp", "scf_type": "df"},
        method="b3lyp",
        calc_type="energy",
    )


@pytest.fixture
def dual_calc() -> Calculation:
    """Fixture for sample Calculation."""
    return Calculation(
        program="psi4",
        program_keywords={"dft_functional": "b3lyp", "scf_type": "df"},
        super_program="geomeTRIC",
        super_keywords={
            "constraints": {
                "freeze": [{"type": "distance", "indices": [0, 1], "value": 1.5}]
            }
        },
        method="b3lyp",
        calc_type="energy",
    )


@pytest.fixture
def prog_out() -> ProgramOutput:
    """Fixture for sample ProgramOutput."""
    prog_out_json = DATA_PATH / "energy_program_output.json"
    return ProgramOutput.model_validate_json(prog_out_json.read_bytes())


@pytest.fixture
def geo() -> Geometry:
    """Fixture for sample Geometry."""
    return Geometry(
        symbols=["O", "H", "H"],
        coordinates=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]),
        charge=0,
        spin=0,
    )


@pytest.fixture
def geo_row() -> GeometryRow:
    """Fixture for sample Geometry."""
    return GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]),
        charge=0,
        spin=0,
    )


@pytest.fixture
def database(calc_row: CalculationRow, geo_row: GeometryRow) -> Iterator[Database]:
    """In-memory database fixture."""
    db = Database(":memory:")

    db.add(calc_row)
    db.add(geo_row)

    try:
        yield db
    finally:
        db.close()
