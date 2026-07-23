"""Autostorage models tests."""

import time
from unittest import mock

import numpy as np
import pytest
from automol import Algorithm, Identity
from numpy.random import Generator
from scipy.spatial.transform import Rotation
from sqlalchemy import inspect as sa_inspect
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
    TrajectoryRow,
    ValidationRow,
)
from autostorage.exc import MissingPrimaryKeyError, ResultShapeError
from autostorage.models import CalculationTrajectoryLink
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


def test__link_create_rejects_ambiguous_row_type(
    calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that link.create() raises when 2+ unfilled relationships share a type.

    No current `BaseLink` subclass has two relationships to the same row
    type, so this patches `sa_inspect` to simulate one, guarding the
    ambiguity check against silently picking a relationship by declaration
    order if such a link table is ever added.
    """
    real_relationships = list(sa_inspect(CalculationGeometryLink).relationships)
    duplicate_geometry_rel = next(
        rel for rel in real_relationships if rel.key == "geometry"
    )

    with mock.patch("autostorage.models.sa_inspect") as mock_inspect:
        mock_inspect.return_value.relationships = [
            *real_relationships,
            duplicate_geometry_rel,
        ]
        with pytest.raises(ValueError, match="multiple unmatched relationships"):
            CalculationGeometryLink.create(
                geometry_row, calculation_row, role=Role.INPUT
            )


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


def test__calculation_geometry_role_properties(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    calc_geo_link: CalculationGeometryLink,
) -> None:
    """Test that input_geometries/output_geometries filter links by role."""
    output_geometry = GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 0.8], [0, 0, 0], [0.8, 0, 0]]),
        charge=0,
        spin=0,
    )
    output_link = CalculationGeometryLink.create(
        calculation_row, output_geometry, role=Role.OUTPUT
    )
    database.add(calculation_row)
    database.add(geometry_row)
    database.add(calc_geo_link)
    database.add(output_geometry)
    database.add(output_link)
    database.commit()

    assert calculation_row.input_geometries == [geometry_row]
    assert calculation_row.output_geometries == [output_geometry]


def test__calculation_trajectory_role_properties(
    database: Database, calculation_row: CalculationRow
) -> None:
    """Test that input_trajectories/output_trajectories filter links by role."""
    # Committed one at a time: TrajectoryRow has no non-base columns, and
    # SQLite's batched multi-row insert can't apply the created_at
    # server_default to two such rows in a single flush.
    input_trajectory = TrajectoryRow()
    database.add(input_trajectory)
    database.commit()
    output_trajectory = TrajectoryRow()
    database.add(output_trajectory)
    database.commit()

    input_link = CalculationTrajectoryLink.create(
        calculation_row, input_trajectory, role=Role.INPUT
    )
    output_link = CalculationTrajectoryLink.create(
        calculation_row, output_trajectory, role=Role.OUTPUT
    )
    database.add(calculation_row)
    database.add(input_link)
    database.add(output_link)
    database.commit()

    assert calculation_row.input_trajectories == [input_trajectory]
    assert calculation_row.output_trajectories == [output_trajectory]


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


def test__geometry_symbols_immutable_after_insert(
    database: Database, geometry_row: GeometryRow
) -> None:
    """Test that mutating symbols after insert is rejected."""
    database.add(geometry_row)
    database.commit()

    geometry_row.symbols = ["H", "O", "O"]
    database.add(geometry_row)
    with pytest.raises(ValueError, match="symbols"):
        database.commit()


def test__geometry_coordinates_immutable_after_insert(
    database: Database, geometry_row: GeometryRow
) -> None:
    """Test that mutating coordinates after insert is rejected."""
    database.add(geometry_row)
    database.commit()

    geometry_row.coordinates = np.array(geometry_row.coordinates) + 0.1
    database.add(geometry_row)
    with pytest.raises(ValueError, match="coordinates"):
        database.commit()


def test__geometry_charge_and_spin_remain_mutable(
    database: Database, geometry_row: GeometryRow
) -> None:
    """Test that charge/spin can still be updated after insert."""
    database.add(geometry_row)
    database.commit()
    assert geometry_row.id

    geometry_row.charge = 1
    geometry_row.spin = 1
    database.add(geometry_row)
    database.commit()

    fetched = database.get(GeometryRow, geometry_row.id)
    assert fetched.charge == 1
    assert fetched.spin == 1


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


def test__hessian_frequency_cache_invalidated_on_value_update(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    calc_geo_link: CalculationGeometryLink,
    rng: Generator,
) -> None:
    """Test that updating `value` invalidates the cached harmonic frequencies.

    `harmonic_frequencies` is a `functools.cached_property`; `Session.commit()`
    doesn't clear cached-property entries (only mapped attributes), so this
    guards against `invalidate_hessian_frequency_cache` regressing and leaving
    stale frequencies/order behind after an in-place `value` update.
    """
    database.add(calculation_row)
    database.add(geometry_row)
    database.add(calc_geo_link)

    n = geometry_row.atom_count
    hessian = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=rng.uniform(size=(3 * n, 3 * n)),
    )
    database.add(hessian)
    database.commit()

    original_frequencies = hessian.harmonic_frequencies
    assert "harmonic_frequencies" in hessian.__dict__

    hessian.value = rng.uniform(size=(3 * n, 3 * n))
    database.add(hessian)
    database.commit()

    assert hessian.harmonic_frequencies != original_frequencies


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


def test__stationary_inchi_resolves_unattached_geometry_id(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test InChI/conformer identities attach when only `geometry_id` is set.

    Regression test: `add_inchi_identities`/`assign_conformer_ids` must
    resolve the geometry via the session (like the shape/order validators
    do), rather than reading the `.geometry` relationship directly, which
    stays unpopulated until the ORM syncs it.
    """
    database.add(calculation_row)
    database.add(geometry_row)
    database.flush()

    stationary = StationaryPointRow(
        calculation_id=calculation_row.id, geometry_id=geometry_row.id, order=0
    )
    database.add(stationary)
    database.commit()

    assert stationary.identities[0].value == "InChI=1S/H2O/h1H2"
    assert stationary.identity(algorithm=Algorithm.IRMSD) is not None


def test__stationary_identity_matches_by_kind_and_algorithm(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test identity() lookup by kind, algorithm, both, and no match."""
    database.add(calculation_row)
    database.add(geometry_row)

    stationary = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    database.add(stationary)
    database.commit()

    inchi = stationary.identity(kind="stereoisomer")
    assert inchi
    assert inchi.value == "InChI=1S/H2O/h1H2"

    conformer = stationary.identity(algorithm=Algorithm.IRMSD)
    assert conformer
    assert conformer.kind == "conformer"

    assert (
        stationary.identity(kind="stereoisomer", algorithm=Algorithm.RDKIT_INCHI)
        is inchi
    )
    assert stationary.identity(kind="nonexistent") is None


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


def test__hessian_delete_leaves_is_valid_correct_with_remaining_hessian(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that deleting one of two agreeing Hessians keeps is_valid correct."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

    n = geometry_row.atom_count
    hessian1 = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=np.zeros((3 * n, 3 * n)),
    )
    hessian2 = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=np.zeros((3 * n, 3 * n)),
    )
    database.add(hessian1)
    database.add(hessian2)

    stationary = StationaryPointRow(
        calculation=calculation_row, geometry=geometry_row, order=0
    )
    database.add(stationary)
    database.commit()
    assert stationary.is_valid

    database.delete(hessian1)
    assert stationary.is_valid


def test__hessian_delete_leaves_is_valid_untouched_when_no_hessians_remain(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that deleting the last Hessian doesn't reset is_valid to False."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

    n = geometry_row.atom_count
    hessian = HessianRow(
        calculation=calculation_row,
        geometry=geometry_row,
        value=np.zeros((3 * n, 3 * n)),
    )
    database.add(hessian)

    stationary = StationaryPointRow(
        calculation=calculation_row, geometry=geometry_row, order=0
    )
    database.add(stationary)
    database.commit()
    assert stationary.is_valid

    database.delete(hessian)
    assert stationary.is_valid


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


def test__stage_find_or_create_reuses_matching_row(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that find_or_create returns the same row for repeated calls."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

    stationary = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    database.add(stationary)
    database.commit()

    first = StageRow.find_or_create(database, [stationary])
    second = StageRow.find_or_create(database, [stationary])

    assert first.id is not None
    assert first.id == second.id


def test__stage_find_or_create_distinguishes_is_ts(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that find_or_create treats differing is_ts as distinct stages."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

    stationary = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    database.add(stationary)
    database.commit()

    non_ts = StageRow.find_or_create(database, [stationary], is_ts=False)
    ts = StageRow.find_or_create(database, [stationary], is_ts=True)

    assert non_ts.id != ts.id


def test__step_find_or_create_reuses_matching_row(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that find_or_create returns the same row for repeated calls."""
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

    first = StepRow.find_or_create(database, stage1, stage2)
    second = StepRow.find_or_create(database, stage1, stage2)

    assert first.id is not None
    assert first.id == second.id


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


def test__step_rejects_ts_stage_as_stage1_or_stage2(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a TS stage cannot be used as stage1/stage2."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

    stationary1 = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    stationary2 = StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
    database.add(stationary1)
    database.add(stationary2)
    database.commit()

    stage_ts = StageRow(stationaries=[stationary1], is_ts=True)
    stage2 = StageRow(stationaries=[stationary2])
    database.add(stage_ts)
    database.add(stage2)
    database.commit()

    database.add(StepRow(stage1=stage_ts, stage2=stage2))
    with pytest.raises(ValueError, match="transition-state"):
        database.commit()


def test__step_rejects_non_ts_stage_as_stage_ts(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a non-TS stage cannot be used as stage_ts."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

    stationaries = [
        StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
        for _ in range(3)
    ]
    for stationary in stationaries:
        database.add(stationary)
    database.commit()

    stage1, stage2, stage3 = (StageRow(stationaries=[s]) for s in stationaries)
    database.add(stage1)
    database.add(stage2)
    database.add(stage3)
    database.commit()

    database.add(StepRow(stage1=stage1, stage2=stage2, stage_ts=stage3))
    with pytest.raises(ValueError, match="stage_ts"):
        database.commit()


def test__step_accepts_consistent_ts_configuration(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a step with a genuine TS stage commits without error."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.commit()

    stationaries = [
        StationaryPointRow(calculation=calculation_row, geometry=geometry_row)
        for _ in range(3)
    ]
    for stationary in stationaries:
        database.add(stationary)
    database.commit()

    stage1 = StageRow(stationaries=[stationaries[0]])
    stage2 = StageRow(stationaries=[stationaries[1]])
    stage_ts = StageRow(stationaries=[stationaries[2]], is_ts=True)
    database.add(stage1)
    database.add(stage2)
    database.add(stage_ts)
    database.commit()

    step = StepRow(stage1=stage1, stage2=stage2, stage_ts=stage_ts)
    database.add(step)
    database.commit()

    assert step.id is not None
    assert not step.is_barrierless


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
