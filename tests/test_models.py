"""Test for models module."""

import numpy as np
from automol import Geometry
from automol.geom import geometry_hash
from qcdata import ProgramOutput

from autostore import (
    Calculation,
    CalculationRow,
    Database,
    GeometryRow,
    StationaryPointRow,
)
from autostore.utils import verify_single_iteration


def test__calculation_calculation_row_equivalence(
    calc: Calculation, calc_row: CalculationRow
) -> None:
    """Test data persistence for Calculation -> CalculationRow."""
    assert calc.program == calc_row.program
    assert calc.program_keywords == calc_row.program_keywords
    assert calc.super_program == calc_row.super_program
    assert calc.super_keywords == calc_row.super_keywords
    assert calc.cmdline_args == calc_row.cmdline_args
    assert calc.calc_type == calc_row.calc_type
    assert calc.method == calc_row.method
    assert calc.basis == calc_row.basis


def test__calculation_from_program_output(
    blank_database: Database, prog_out: ProgramOutput
) -> None:
    """Test data persistence in CalculationRow -> ProgramInput -> Geometry roundtrip."""
    calc_row = CalculationRow.from_program_output(prog_out)
    blank_database.add(calc_row, eager_load=True)
    assert calc_row.program == prog_out.provenance.program
    assert calc_row.provenance.program_version == prog_out.provenance.program_version


def test__geometry_geometry_row_equivalence(geo: Geometry) -> None:
    """Test data persistence for Geometry -> GeometryRow."""
    geo_row = GeometryRow.from_geometry(geo=geo)
    assert np.array_equal(a1=geo_row.symbols, a2=geo.symbols)
    assert np.allclose(a=geo_row.coordinates, b=geo.coordinates)
    assert geo_row.charge == geo.charge
    assert geo_row.spin == geo_row.spin


def test__geometry_structure_roundtrip(geo_row: GeometryRow) -> None:
    """Test data persistence in Geometry -> Structure -> Geometry roundtrip."""
    struc = geo_row.structure()
    geo_row_round_trip = GeometryRow.from_structure(struc=struc)
    assert np.array_equal(a1=geo_row.symbols, a2=geo_row_round_trip.symbols)
    assert np.allclose(a=geo_row.coordinates, b=geo_row_round_trip.coordinates)
    assert geo_row.charge == geo_row_round_trip.charge
    assert geo_row.spin == geo_row_round_trip.spin
    assert geo_row.hash == geometry_hash(geo=geo_row_round_trip)


def test__stationary_point_inchi(stationary_database: Database) -> None:
    """Test InChI identity tagging upon StationaryRow addition."""
    matches = stationary_database.find(StationaryPointRow.partial(), eager_load=True)
    match = verify_single_iteration(matches)
    assert match.identities  # ty:ignore[unresolved-attribute]
