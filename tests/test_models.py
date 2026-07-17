"""Autostorage models tests."""

import numpy as np
import pytest
from automol import Algorithm, Identity
from numpy.random import Generator

from autostorage import (
    CalculationGeometryLink,
    CalculationRow,
    Database,
    GeometryRow,
    GradientRow,
    HessianRow,
    StageRow,
    StationaryPointRow,
    StepRow,
)
from autostorage.exc import MissingPrimaryKeyError, ResultShapeError


def test__gradient_shape(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    calc_geo_link: CalculationGeometryLink,
    rng: Generator,
) -> None:
    """Test gradient shape is validated before committing to database."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.add(calc_geo_link)

    gradient = GradientRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=rng.uniform(size=2),
    )
    database.add(gradient)
    with pytest.raises(ResultShapeError):
        database.commit()


def test__hessian_shape(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    calc_geo_link: CalculationGeometryLink,
    rng: Generator,
) -> None:
    """Test hessian shape is validated before committing to database."""
    calculation_row.save(database)
    geometry_row.save(database)
    calc_geo_link.save(database)

    hess = geometry_row.hessian(
        calc=calculation_row, value=list(rng.uniform(size=(3, 2)))
    )
    database.add(hess)

    with pytest.raises(ResultShapeError):
        database.commit()


def test__hessian_properties(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    calc_geo_link: CalculationGeometryLink,
    rng: Generator,
) -> None:
    """Test hessian harmonic frequencies and order properties."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.add(calc_geo_link)

    n = geometry_row.atom_count
    hessian = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=rng.uniform(size=(3 * n, 3 * n)),
    )
    assert hessian.harmonic_frequencies
    assert hessian.order


def test__result_query(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    calc_geo_link: CalculationGeometryLink,
    rng: Generator,
) -> None:
    """Test querying of result tables."""
    calculation_row.save(database)
    geometry_row.save(database)
    calc_geo_link.save(database)

    n = geometry_row.atom_count
    hess = geometry_row.hessian(
        calc=calculation_row, value=list(rng.uniform(size=(3 * n, 3 * n)))
    )
    database.add(hess)

    database.commit()

    hess2 = HessianRow.query(database, geo=geometry_row, model=calculation_row.model)
    assert hess2
    assert hess2.id == hess.id


def test__stationary_inchi(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test InChI is attached before committing to database."""
    database.add(calculation_row)
    database.add(geometry_row)

    stationary = StationaryPointRow(
        calculation=calculation_row, geometry=geometry_row, order=0
    )
    database.add(stationary)
    database.commit()

    assert stationary.identities[0].value == "InChI=1S/H2O/h1H2"


def test__stationary_order_hessian_first(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test stationary point order is validated when geometry Hessian is present.

    Corrects a valid StationaryPointRow marked as invalid.
    """
    database.add(calculation_row)
    database.add(geometry_row)

    n = geometry_row.atom_count
    hessian_row = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=np.zeros((3 * n, 3 * n)),
    )
    database.add(hessian_row)

    stationary = StationaryPointRow(
        calculation=calculation_row, geometry=geometry_row, order=0, is_valid=False
    )
    database.add(stationary)
    assert not stationary.is_valid

    database.commit()
    assert stationary.is_valid


def test__stationary_order_hessian_second(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test stationary point order is validated when geometry Hessian is present.

    Corrects an invalid StationaryPointRow marked as valid.
    """
    database.add(calculation_row)
    database.add(geometry_row)

    stationary = StationaryPointRow(
        calculation=calculation_row, geometry=geometry_row, order=1, is_valid=True
    )
    database.add(stationary)
    assert stationary.is_valid

    n = geometry_row.atom_count
    hessian_row = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=np.zeros((3 * n, 3 * n)),
    )
    database.add(hessian_row)

    database.commit()
    assert not stationary.is_valid


def test__stationary_query(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test querying of stationary points."""
    calculation_row.save(database)
    geometry_row.save(database)

    stationary = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    database.add(stationary)

    ident = Identity.from_geometry(geo=geometry_row, algorithm=Algorithm.RDKIT_INCHI)
    stationary2 = StationaryPointRow.query(
        database, ident=ident, model=calculation_row.model
    )

    assert stationary2
    assert stationary2.id == stationary.id


def test__invalid_stationary_query(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test invalid querying of stationary points."""
    ident = Identity.from_geometry(geo=geometry_row, algorithm=Algorithm.RDKIT_INCHI)
    with pytest.raises(MissingPrimaryKeyError):
        StationaryPointRow.query(database, ident=ident, model=calculation_row.model)


def test__stage_and_step_query(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test querying of stages and steps built on the chainable Query API."""
    calculation_row.save(database)
    geometry_row.save(database)

    stationary1 = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    stationary2 = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    database.add(stationary1)
    database.add(stationary2)
    database.commit()

    stage1 = StageRow(stationaries=[stationary1])
    stage2 = StageRow(stationaries=[stationary2])
    database.add(stage1)
    database.add(stage2)
    database.commit()

    stage_match = StageRow.query(database, [stationary1])
    assert stage_match
    assert stage_match.id == stage1.id

    step = StepRow(stage1=stage1, stage2=stage2)
    database.add(step)
    database.commit()

    step_match = StepRow.query(database, stage1, stage2)
    assert step_match
    assert step_match.id == step.id
