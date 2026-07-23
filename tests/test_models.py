"""Autostorage models tests."""

import numpy as np
import pytest
from automol import Algorithm, Identity
from numpy.random import Generator
from scipy.spatial.transform import Rotation

from autostorage import (
    CalculationGeometryLink,
    CalculationRow,
    Database,
    GeometryRow,
    GradientRow,
    HessianRow,
    ModelRow,
    StageRow,
    StationaryPointRow,
    StepRow,
)
from autostorage.exc import MissingPrimaryKeyError, ResultShapeError


def test__model_find_or_create_reuses_matching_row(database: Database) -> None:
    """Test that find_or_create returns the same row for repeated calls."""
    first = ModelRow.find_or_create(database, program="orca", method="xtb")
    second = ModelRow.find_or_create(database, program="orca", method="xtb")

    assert first.id is not None
    assert first.id == second.id


def test__model_find_or_create_distinguishes_basis(database: Database) -> None:
    """Test that find_or_create treats a differing basis as a distinct model."""
    no_basis = ModelRow.find_or_create(database, program="orca", method="xtb")
    with_basis = ModelRow.find_or_create(
        database, program="orca", method="xtb", basis="def2-svp"
    )

    assert no_basis.id != with_basis.id


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


def _hooh_geometry_row(dihedral_deg: float) -> GeometryRow:
    """Build an HOOH GeometryRow at a given H-O-O-H dihedral angle."""
    roo, roh, hoo_ang = 1.45, 0.97, np.radians(100.0)
    dih = np.radians(dihedral_deg)
    o1 = np.array([0, 0, 0])
    o2 = np.array([roo, 0, 0])
    h1 = o1 + roh * np.array([-np.cos(hoo_ang), np.sin(hoo_ang), 0])
    base = roh * np.array([np.cos(hoo_ang), np.sin(hoo_ang), 0])
    rot = np.array(
        [
            [1, 0, 0],
            [0, np.cos(dih), -np.sin(dih)],
            [0, np.sin(dih), np.cos(dih)],
        ]
    )
    h2 = o2 + rot @ base
    coordinates = np.array([h1, o1, o2, h2])
    return GeometryRow(
        symbols=["H", "O", "O", "H"], coordinates=coordinates, charge=0, spin=0
    )


def _jittered_copy(geometry_row: GeometryRow, rng: Generator) -> GeometryRow:
    """Build a small-noise, rotated, translated copy of a geometry."""
    coordinates = np.array(geometry_row.coordinates)
    coordinates = coordinates + rng.normal(scale=0.01, size=coordinates.shape)
    rot = Rotation.from_euler("xyz", [30, 20, 10], degrees=True)
    coordinates = rot.apply(coordinates) + np.array([3.0, 3.0, 3.0])
    return GeometryRow(
        symbols=list(geometry_row.symbols),
        coordinates=coordinates,
        charge=geometry_row.charge,
        spin=geometry_row.spin,
    )


def test__conformer_identity_merge_on_duplicate_geometry(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    rng: Generator,
) -> None:
    """Test that near-identical geometries share one conformer identity."""
    duplicate_geometry = _jittered_copy(geometry_row, rng)

    database.add(calculation_row)
    database.add(geometry_row)
    database.add(duplicate_geometry)

    stationary1 = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    stationary2 = StationaryPointRow(
        calculation=calculation_row, geometry=duplicate_geometry
    )
    database.add(stationary1)
    database.add(stationary2)
    database.commit()

    conformer1 = next(i for i in stationary1.identities if i.kind == "conformer")
    conformer2 = next(i for i in stationary2.identities if i.kind == "conformer")
    assert conformer1.id == conformer2.id


def test__conformer_identity_split_on_distinct_conformer(
    database: Database, calculation_row: CalculationRow
) -> None:
    """Test that geometrically distinct conformers of the same species split."""
    anti = _hooh_geometry_row(180)
    gauche = _hooh_geometry_row(60)

    database.add(calculation_row)
    database.add(anti)
    database.add(gauche)

    stationary1 = StationaryPointRow(calculation=calculation_row, geometry=anti)
    stationary2 = StationaryPointRow(calculation=calculation_row, geometry=gauche)
    database.add(stationary1)
    database.add(stationary2)
    database.commit()

    conformer1 = next(i for i in stationary1.identities if i.kind == "conformer")
    conformer2 = next(i for i in stationary2.identities if i.kind == "conformer")
    assert conformer1.value != conformer2.value


def test__conformer_group_id_increments_across_distinct_species_in_one_flush(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    rng: Generator,
) -> None:
    """Test that one flush assigns distinct group ids to distinct species."""
    duplicate_geometry = _jittered_copy(geometry_row, rng)
    hooh_geometry = _hooh_geometry_row(180)

    database.add(calculation_row)
    database.add(geometry_row)
    database.add(duplicate_geometry)
    database.add(hooh_geometry)

    water1 = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    water2 = StationaryPointRow(
        calculation=calculation_row, geometry=duplicate_geometry
    )
    hooh = StationaryPointRow(calculation=calculation_row, geometry=hooh_geometry)
    database.add(water1)
    database.add(water2)
    database.add(hooh)
    database.commit()

    water1_conf = next(i for i in water1.identities if i.kind == "conformer")
    water2_conf = next(i for i in water2.identities if i.kind == "conformer")
    hooh_conf = next(i for i in hooh.identities if i.kind == "conformer")

    assert water1_conf.id == water2_conf.id
    assert hooh_conf.id != water1_conf.id


def test__conformer_identity_idempotent_on_second_flush(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that re-flushing an already-committed stationary point is idempotent."""
    database.add(calculation_row)
    database.add(geometry_row)

    stationary = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    database.add(stationary)
    database.commit()

    conformer_id = next(i for i in stationary.identities if i.kind == "conformer").id

    stationary.order = 1
    database.add(stationary)
    database.commit()

    conformer_identities = [i for i in stationary.identities if i.kind == "conformer"]
    assert len(conformer_identities) == 1
    assert conformer_identities[0].id == conformer_id
