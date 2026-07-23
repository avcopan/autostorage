"""Autostorage models tests."""

import time

import numpy as np
import pytest
from automol import Algorithm, Identity
from numpy.random import Generator
from scipy.spatial.transform import Rotation
from sqlalchemy.exc import IntegrityError

from autostorage import (
    CalcStatus,
    CalcType,
    CalculationGeometryLink,
    CalculationRow,
    Database,
    EnergyRow,
    GeometryRow,
    GradientRow,
    HessianRow,
    ModelRow,
    StageRow,
    StationaryPointRow,
    StepRow,
    ValidationRow,
)
from autostorage.exc import MissingPrimaryKeyError, ResultShapeError
from autostorage.types import Role


def test__link_create_matches_rows_by_type(
    calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that link.create() matches rows to relationships regardless of order."""
    link = CalculationGeometryLink.create(
        geometry_row, calculation_row, role=Role.INPUT
    )

    assert link.calculation is calculation_row
    assert link.geometry is geometry_row
    assert link.role == Role.INPUT


def test__link_create_rejects_unmatched_row(
    calculation_row: CalculationRow, model_row: ModelRow
) -> None:
    """Test that link.create() raises when a row has no matching relationship."""
    with pytest.raises(ValueError, match="no unmatched relationship"):
        CalculationGeometryLink.create(calculation_row, model_row, role=Role.INPUT)


def test__row_timestamps_set_on_create(database: Database) -> None:
    """Test that created_at/updated_at are populated by the database on insert."""
    row = ModelRow(program="orca", method="xtb")
    database.add(row)
    database.commit()

    assert row.created_at is not None
    assert row.updated_at is not None


def test__row_updated_at_advances_on_update(database: Database) -> None:
    """Test that updated_at advances on a later commit while created_at doesn't."""
    row = ModelRow(program="orca", method="xtb")
    database.add(row)
    database.commit()
    created_at, updated_at = row.created_at, row.updated_at
    assert created_at is not None
    assert updated_at is not None

    # SQLite's CURRENT_TIMESTAMP has one-second resolution.
    time.sleep(1.1)
    row.basis = "def2-svp"
    database.add(row)
    database.commit()

    assert row.updated_at is not None
    assert row.created_at == created_at
    assert row.updated_at > updated_at


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


def test__model_null_safe_index_catches_duplicate(database: Database) -> None:
    """Test that a direct duplicate insert (bypassing find_or_create) is rejected.

    `unique_model` alone doesn't catch this, since SQL treats NULL as distinct
    from itself; `unique_model_null_safe` is the defense-in-depth index that does.
    """
    database.add(ModelRow(program="orca", method="xtb"))
    database.add(ModelRow(program="orca", method="xtb"))

    with pytest.raises(IntegrityError):
        database.commit()


def test__calculation_default_status_is_pending(model_row: ModelRow) -> None:
    """Test that a bare CalculationRow defaults to PENDING with no error message."""
    calculation = CalculationRow(model=model_row, calc_type=CalcType.UNDEFINED)

    assert calculation.status == CalcStatus.PENDING
    assert calculation.error_message is None


def test__calculation_status_transitions(
    database: Database, model_row: ModelRow
) -> None:
    """Test that status/error_message round-trip through the database."""
    calculation = CalculationRow(
        model=model_row,
        calc_type=CalcType.UNDEFINED,
        status=CalcStatus.FAILED,
        error_message="boom",
    )
    database.add(calculation)
    database.commit()
    assert calculation.id is not None

    fetched = database.get(CalculationRow, calculation.id)
    assert fetched.status == CalcStatus.FAILED
    assert fetched.error_message == "boom"


def test__validation_requires_calculation(database: Database) -> None:
    """Test that a ValidationRow without a calculation is rejected."""
    database.add(ValidationRow(method="irc"))

    with pytest.raises(IntegrityError):
        database.commit()


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
    database.add(calculation_row)
    database.add(geometry_row)
    database.add(calc_geo_link)
    database.commit()

    hess = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=rng.uniform(size=(3, 2)),
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
    database.add(calculation_row)
    database.add(geometry_row)
    database.add(calc_geo_link)
    database.commit()

    n = geometry_row.atom_count
    hess = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=rng.uniform(size=(3 * n, 3 * n)),
    )
    database.add(hess)

    database.commit()

    hess2 = HessianRow.query(database, geo=geometry_row, model=calculation_row.model)
    assert hess2
    assert hess2.id == hess.id


def test__provenance_query_matches_regardless_of_dict_key_order(
    database: Database, geometry_row: GeometryRow, model_row: ModelRow
) -> None:
    """Test that provenance-filtered queries ignore dict key insertion order.

    SQLite JSON columns compare by exact serialized text, so two dicts built with
    different key insertion order would previously fail to match even though
    they're equal in Python; `Database`'s `json_serializer` canonicalizes key
    order on write to fix this.
    """
    calculation = CalculationRow(
        model=model_row, calc_type=CalcType.ENERGY, input_provenance={"b": 1, "a": 2}
    )
    database.add(calculation)
    database.add(geometry_row)
    database.commit()

    energy = EnergyRow(calculation=calculation, geometry=geometry_row, value=-1.0)
    database.add(energy)
    database.commit()

    found = EnergyRow.query(
        database, geo=geometry_row, model=model_row, prov={"a": 2, "b": 1}
    )
    assert found
    assert found.id == energy.id


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
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

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
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

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


def test__step_null_safe_index_catches_barrierless_duplicate(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a direct duplicate barrierless step (bypassing StepRow.query) fails.

    `unq_step_stages` alone doesn't catch this, since `stage_id_ts` is NULL for
    both rows and SQL treats NULL as distinct from itself; `unq_step_stages_null_safe`
    is the defense-in-depth index that does.
    """
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

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

    database.add(StepRow(stage1=stage1, stage2=stage2))
    database.add(StepRow(stage1=stage1, stage2=stage2))

    with pytest.raises(IntegrityError):
        database.commit()


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
