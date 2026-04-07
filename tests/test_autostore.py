"""autostore tests."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from automol import Geometry
from qcdata import CalcType, ProgramOutput

from autostore import Calculation, Database, models, qc


@pytest.fixture
def database() -> Iterator[Database]:
    """In-memory database fixture."""
    db = Database(":memory:")
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def water() -> Geometry:
    """Water geometry fixture."""
    return Geometry(
        symbols=["O", "H", "H"],
        coordinates=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],  # ty:ignore[invalid-argument-type]
    )


@pytest.fixture
def h2() -> Geometry:
    """Water geometry fixture."""
    return Geometry(
        symbols=["H", "H"],
        coordinates=[[0, 0, 0], [0, 0.74, 0]],  # ty:ignore[invalid-argument-type]
    )


@pytest.fixture
def xtb_calculation() -> Calculation:
    """XTB calculation fixture."""
    return Calculation(program="crest", method="gfnff")


@pytest.fixture
def water_xtb_energy_results() -> ProgramOutput:
    """Water energy calculation results fixture."""
    return ProgramOutput.model_validate(
        {
            "input_data": {
                "structure": {
                    "symbols": ["O", "H", "H"],
                    "geometry": [
                        [0.0, 0.0, 0.0],
                        [1.8897261259082012, 0.0, 0.0],
                        [0.0, 1.8897261259082012, 0.0],
                    ],
                    "charge": 0,
                    "multiplicity": 1,
                },
                "model": {"method": "gfn2", "basis": None},
                "calctype": "energy",
            },
            "success": True,
            "data": {"energy": -5.062316802835694},
            "provenance": {"program": "crest", "program_version": "3.0.2"},
        }
    )


@pytest.fixture
def h2_gfnff_stationary_results() -> ProgramOutput:
    """Water energy calculation results fixture."""
    with (Path(__file__).parent / "stationary.json").open(encoding="utf-8") as f:
        data = json.load(f)

    return ProgramOutput.model_validate(data)


def test_energy(
    water: Geometry,
    water_xtb_energy_results: ProgramOutput,
    database: Database,
) -> None:
    """Test writing and reading of the energy and corresponding database rows."""
    # Instantiate GeometryRow, write to database, and ensure correct hash population
    geom_row = models.GeometryRow(**water.model_dump())
    geom_id = database.write(row=geom_row)
    assert database.query(model=models.GeometryRow, hash=water.hash)[0] == geom_id

    # Instantiate CalculationRow, set input geometry id, write to database,
    # and ensure correct calctype
    calc_row = qc.prog_output.calc_row(water_xtb_energy_results)
    calc_row.input_geometry_id = geom_id
    calc_id = database.write(row=calc_row)  # ty:ignore[invalid-argument-type]
    assert (
        database.query(model=models.CalculationRow, calctype=CalcType.energy)[0]
        == calc_id
    )

    # Instantiate EnergyRow, set geometry and calculation ids, write to database,
    # and ensure correct energy value
    ene_row = models.EnergyRow(
        geometry_id=geom_id,
        calculation_id=calc_id,
        value=water_xtb_energy_results.data.energy,
    )
    ene_id = database.write(row=ene_row)
    assert database.query(model=models.EnergyRow, value=-5.062316802835694)[0] == ene_id


def test_stationary(
    h2: Geometry,
    h2_gfnff_stationary_results: ProgramOutput,
    database: Database,
) -> None:
    """Test writing and reading of the energy and corresponding database rows."""
    # Instantiate GeometryRow, write to database, and ensure correct hash population
    input_geom_row = models.GeometryRow(**h2.model_dump())
    input_geom_id = database.write(row=input_geom_row)
    assert database.query(model=models.GeometryRow, hash=h2.hash)[0] == input_geom_id

    # Instantiate CalculationRow, set input geometry id, write to database,
    # and ensure correct calctype
    calc_row = qc.prog_output.calc_row(h2_gfnff_stationary_results)
    calc_row.input_geometry_id = input_geom_id
    calc_id = database.write(row=calc_row)  # ty:ignore[invalid-argument-type]
    assert (
        database.query(model=models.CalculationRow, calctype=CalcType.optimization)[0]
        == calc_id
    )

    # Instantiate EnergyRow, set geometry and calculation ids, write to database,
    # and ensure it's equal to input model
    stp_row = models.StationaryPointRow(
        geometry_id=input_geom_id, calculation_id=calc_id, order=1
    )
    stp_id = database.write(row=stp_row)
    stp_row_fetch = database.fetch(model=models.StationaryPointRow, row_id=stp_id)

    assert stp_row == stp_row_fetch
