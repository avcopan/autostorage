"""Fixtures for tests."""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from automol import Geometry
from qcdata import ProgramOutput

from autostore import (
    Calculation,
    CalculationGeometryLink,
    CalculationRow,
    Database,
    GeometryRow,
    StationaryPointRow,
)
from autostore.types import Role

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
def calc_row(calc: Calculation) -> CalculationRow:
    """Fixture for sample CalculationRow."""
    return CalculationRow.from_calculation(calc=calc)


@pytest.fixture
def dual_calc_row(dual_calc: Calculation) -> CalculationRow:
    """Fixture for sample CalculationRow with DualProgramInput attributes."""
    return CalculationRow.from_calculation(calc=dual_calc)


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
def geo_row(geo: Geometry) -> GeometryRow:
    """Fixture for sample GeometryRow."""
    return GeometryRow.from_geometry(geo)


@pytest.fixture
def blank_database() -> Iterator[Database]:
    """In-memory blank database fixture."""
    db = Database(":memory:")
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def calc_geo_database(
    calc_row: CalculationRow, geo_row: GeometryRow
) -> Iterator[Database]:
    """Database fixture with CalculationRow, GeometryRow, CalculationGeometryLink."""
    db = Database(":memory:")
    db.add(calc_row)
    db.add(geo_row)

    assert calc_row.id is not None
    assert geo_row.id is not None

    calc_geo_link = CalculationGeometryLink(
        calculation_id=calc_row.id, geometry_id=geo_row.id, role=Role.input
    )
    db.add(row=calc_geo_link)

    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def stationary_database(
    calc_row: CalculationRow, geo_row: GeometryRow
) -> Iterator[Database]:
    """Database fixture with CalculationRow, GeometryRow, CalculationGeometryLink."""
    db = Database(":memory:")
    db.add(calc_row)
    db.add(geo_row)

    assert calc_row.id is not None
    assert geo_row.id is not None

    stp_row = StationaryPointRow(
        calculation_id=calc_row.id, geometry_id=geo_row.id, order=0, is_pseudo=False
    )
    db.add(row=stp_row)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def geo_in_database(geo_row: GeometryRow) -> Iterator[Database]:
    """In-memory database with geometry row fixture."""
    db = Database(":memory:")
    db.add(row=geo_row)
    try:
        yield db
    finally:
        db.close()
