"""Tests for autostorage.merge."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from automol import Algorithm
from sqlalchemy import text
from sqlmodel import SQLModel, select

from autostorage import (
    CalculationRow,
    Database,
    GeometryRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
    ModelRow,
    StageRow,
    StationaryPointRow,
    StepRow,
)
from autostorage.exc import ResultShapeError
from autostorage.merge import _fk_targets, _ordered_models
from autostorage.models import StationaryIdentityLink
from autostorage.types import CalcType, CompressedArrayTypeDecorator


@pytest.fixture
def target() -> Iterator[Database]:
    """In-memory database fixture, playing the role of a merge's target."""
    db = Database(":memory:")
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def source() -> Iterator[Database]:
    """In-memory database fixture, playing the role of a merge's source."""
    db = Database(":memory:")
    try:
        yield db
    finally:
        db.close()


def _water_geometry() -> GeometryRow:
    """Build a water GeometryRow."""
    return GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=np.array([[0.0, 0.0, 0.0], [0.96, 0.0, 0.0], [-0.24, 0.93, 0.0]]),
        charge=0,
        spin=0,
    )


def _add_water_stationary(db: Database) -> StationaryPointRow:
    """Add a model/calculation/geometry/stationary-point chain for water to `db`."""
    model = ModelRow.find_or_create(db, program="orca", method="xtb")
    calculation = CalculationRow(model=model, calc_type=CalcType.OPT)
    db.add(calculation)
    geometry = _water_geometry()
    db.add(geometry)
    db.flush()

    stationary = StationaryPointRow(
        calculation_id=calculation.id, geometry_id=geometry.id
    )
    db.add(stationary)
    db.commit()
    return stationary


# --- Preconditions -----------------------------------------------------------


def test__merge_from_self_raises(target: Database) -> None:
    """Test that merging a database into itself is rejected."""
    with pytest.raises(ValueError, match="itself"):
        target.merge_from(target)


def test__distinct_in_memory_databases_never_collide(
    target: Database, source: Database
) -> None:
    """Test that two distinct `:memory:` databases are never treated as the same."""
    report = target.merge_from(source)
    assert report.copied == {}


def test__same_on_disk_file_collides(tmp_path: Path) -> None:
    """Test that two `Database`s opened on the same on-disk file are rejected."""
    path = tmp_path / "shared.db"
    a = Database(path)
    b = Database(path)
    try:
        with pytest.raises(ValueError, match="itself"):
            a.merge_from(b)
    finally:
        a.close()
        b.close()


def test__missing_column_fails_precondition(tmp_path: Path) -> None:
    """Test that a source DB missing an expected column fails before any row copies."""
    path = tmp_path / "stale.db"
    Database(path).close()

    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE geometry DROP COLUMN spin")
    conn.commit()
    conn.close()

    source_db = Database(path)
    target_db = Database(":memory:")
    try:
        with pytest.raises(ValueError, match="spin"):
            target_db.merge_from(source_db)
    finally:
        source_db.close()
        target_db.close()


# --- FK remapping --------------------------------------------------------


def test__multi_tier_fk_remapping(target: Database, source: Database) -> None:
    """Test that FKs resolve to newly-copied rows across a full model->step chain.

    `target` is pre-populated with an unrelated model/calculation/geometry/
    stationary/stage chain of its own first, so every table's autoincrement
    ids advance past 1 before the merge -- a broken remap that left a raw
    source id in place could then plausibly resolve to one of these decoy
    rows instead of failing outright, which the final content check catches
    (the decoy geometry is a single helium atom, trivially distinguishable
    from the water geometries actually being merged).
    """
    decoy_model = ModelRow.find_or_create(target, program="decoy", method="decoy")
    decoy_calculation = CalculationRow(model=decoy_model, calc_type=CalcType.OPT)
    target.add(decoy_calculation)
    decoy_geometry = GeometryRow(
        symbols=["He"], coordinates=np.zeros((1, 3)), charge=0, spin=0
    )
    target.add(decoy_geometry)
    target.flush()
    decoy_stationary = StationaryPointRow(
        calculation_id=decoy_calculation.id, geometry_id=decoy_geometry.id
    )
    target.add(decoy_stationary)
    target.commit()
    target.add(StageRow(stationaries=[decoy_stationary]))
    target.commit()

    model = ModelRow.find_or_create(source, program="orca", method="xtb")
    calculation = CalculationRow(model=model, calc_type=CalcType.OPT)
    source.add(calculation)
    source.flush()

    geometry1 = _water_geometry()
    geometry2 = GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=np.array([[0.0, 0.0, 0.0], [1.1, 0.0, 0.0], [-0.3, 1.0, 0.0]]),
        charge=0,
        spin=0,
    )
    source.add(geometry1)
    source.add(geometry2)
    source.flush()

    stationary1 = StationaryPointRow(
        calculation_id=calculation.id, geometry_id=geometry1.id
    )
    stationary2 = StationaryPointRow(
        calculation_id=calculation.id, geometry_id=geometry2.id
    )
    source.add(stationary1)
    source.add(stationary2)
    source.commit()

    stage1 = StageRow(stationaries=[stationary1])
    stage2 = StageRow(stationaries=[stationary2])
    source.add(stage1)
    source.add(stage2)
    source.commit()

    StepRow.find_or_create(source, stage1, stage2)

    target.merge_from(source)

    merged_steps = target.exec_all(select(StepRow))
    assert len(merged_steps) == 1
    (merged_step,) = merged_steps
    assert merged_step.stage_id_ts is None

    merged_geometries = {
        stationary.geometry.coordinates.tobytes()
        for stage_id in (merged_step.stage_id1, merged_step.stage_id2)
        for stationary in target.get(StageRow, stage_id).stationaries
    }
    assert merged_geometries == {
        geometry1.coordinates.tobytes(),
        geometry2.coordinates.tobytes(),
    }


# --- ModelRow/IdentityRow dedup ----------------------------------------------


def test__model_dedup_distinguishes_null_basis(
    target: Database, source: Database
) -> None:
    """Test that a differing basis is kept distinct, matching basis=None is reused."""
    ModelRow.find_or_create(target, program="orca", method="xtb")
    before = len(target.exec_all(select(ModelRow)))

    ModelRow.find_or_create(source, program="orca", method="xtb")
    ModelRow.find_or_create(source, program="orca", method="xtb", basis="def2-svp")

    report = target.merge_from(source)

    assert report.reused["model"] == 1
    assert report.copied["model"] == 1
    assert len(target.exec_all(select(ModelRow))) == before + report.copied["model"]


# --- GeometryRow dedup --------------------------------------------------------


def test__geometry_dedup_reuses_identical_geometry(
    target: Database, source: Database
) -> None:
    """Test that an identical geometry is reused, and dependents resolve to it."""
    target_geometry = _water_geometry()
    target.add(target_geometry)
    target.commit()
    before = len(target.exec_all(select(GeometryRow)))

    _add_water_stationary(source)

    report = target.merge_from(source)

    assert report.reused["geometry"] == 1
    assert report.copied["geometry"] == 0
    assert len(target.exec_all(select(GeometryRow))) == before

    (merged_stationary,) = target.exec_all(select(StationaryPointRow))
    assert merged_stationary.geometry_id == target_geometry.id


# --- Identity/events interaction ---------------------------------------------


def test__conformer_and_inchi_collapse_across_merged_databases(
    target: Database, source: Database
) -> None:
    """Test that a matching conformer from source and target share one identity."""
    stationary_t = _add_water_stationary(target)
    _add_water_stationary(source)

    target.merge_from(source)

    stationaries = target.exec_all(select(StationaryPointRow))
    merged_stationary = next(s for s in stationaries if s.id != stationary_t.id)

    conformer_t = stationary_t.identity(kind=Algorithm.IRMSD.kind)
    conformer_merged = merged_stationary.identity(kind=Algorithm.IRMSD.kind)
    assert conformer_t is not None
    assert conformer_merged is not None
    assert conformer_t.id == conformer_merged.id

    inchi_t = stationary_t.identity(algorithm=Algorithm.RDKIT_INCHI)
    inchi_merged = merged_stationary.identity(algorithm=Algorithm.RDKIT_INCHI)
    assert inchi_t is not None
    assert inchi_merged is not None
    assert inchi_t.id == inchi_merged.id


def test__smiles_extra_and_identity_links_not_duplicated(
    target: Database, source: Database
) -> None:
    """Test that the auto-attached SMILES extra/links aren't duplicated by a merge."""
    _add_water_stationary(target)
    _add_water_stationary(source)

    target.merge_from(source)

    (extra,) = target.exec_all(select(IdentityExtraRow))
    assert extra.attribute == "smiles"

    # Each stationary point shares the same two identities (InChI + conformer)
    # rather than getting its own duplicate pair.
    stationaries = target.exec_all(select(StationaryPointRow))
    shared_identity_kinds = {Algorithm.RDKIT_INCHI.kind, Algorithm.IRMSD.kind}
    links = target.exec_all(select(StationaryIdentityLink))
    assert len(links) == len(stationaries) * len(shared_identity_kinds)


def test__non_auto_managed_identity_is_explicitly_deduped(
    target: Database, source: Database
) -> None:
    """Test that an identity kind other than InChI/conformer is find-or-created.

    `Algorithm.RDKIT_SMILES` is never persisted as a standalone `IdentityRow`
    by any event (it's only ever folded into an `IdentityExtraRow`), so this
    exercises the "explicit copy" branch of identity handling directly,
    using a manually-attached identity the way a caller outside the
    InChI/conformer auto-generation path might.
    """
    stationary_t = _add_water_stationary(target)
    smiles_t = IdentityRow.find_or_create(
        target, algorithm=Algorithm.RDKIT_SMILES, value="O"
    )
    assert stationary_t.id is not None
    assert smiles_t.id is not None
    target.add(
        StationaryIdentityLink(stationary_id=stationary_t.id, identity_id=smiles_t.id)
    )
    target.commit()

    stationary_s = _add_water_stationary(source)
    smiles_s = IdentityRow.find_or_create(
        source, algorithm=Algorithm.RDKIT_SMILES, value="O"
    )
    assert stationary_s.id is not None
    assert smiles_s.id is not None
    source.add(
        StationaryIdentityLink(stationary_id=stationary_s.id, identity_id=smiles_s.id)
    )
    source.commit()

    report = target.merge_from(source)

    assert report.reused["identity"] == 1
    smiles_rows = [
        identity
        for identity in target.exec_all(select(IdentityRow))
        if identity.algorithm == Algorithm.RDKIT_SMILES
    ]
    assert len(smiles_rows) == 1


# --- Atomicity -----------------------------------------------------------


def test__failed_merge_rolls_back_earlier_tiers(
    target: Database, source: Database
) -> None:
    """Test that a validation failure partway through leaves target unchanged.

    The invalid Hessian is planted via raw SQL rather than the ORM, since
    `source`'s own shape-check event would otherwise reject it immediately
    -- this simulates a stale/hand-edited source file, exactly the case
    merge-time validation exists to catch.
    """
    ModelRow.find_or_create(source, program="new-program", method="xtb")

    model = ModelRow.find_or_create(source, program="orca", method="xtb")
    calculation = CalculationRow(model=model, calc_type=CalcType.FREQUENCY)
    source.add(calculation)
    geometry = _water_geometry()
    source.add(geometry)
    source.commit()

    bad_value = CompressedArrayTypeDecorator(dtype=np.float32).process_bind_param(
        np.zeros((2, 2)), None
    )
    with source.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO hessian (geometry_id, calculation_id, value) "
                "VALUES (:geo, :calc, :value)"
            ),
            {"geo": geometry.id, "calc": calculation.id, "value": bad_value},
        )

    with pytest.raises(ResultShapeError):
        target.merge_from(source)

    assert target.exec_all(select(ModelRow)) == []
    assert target.exec_all(select(HessianRow)) == []


def test__commit_false_leaves_merge_uncommitted(
    target: Database, source: Database
) -> None:
    """Test that commit=False flushes (assigning ids) but doesn't commit."""
    ModelRow.find_or_create(source, program="orca", method="xtb")

    report = target.merge_from(source, commit=False)

    assert report.copied["model"] == 1
    (model,) = target.exec_all(select(ModelRow))
    assert model.id is not None

    target._session.rollback()  # noqa: SLF001
    assert target.exec_all(select(ModelRow)) == []


# --- Generic ordering (private-API safety net) --------------------------


def test__ordered_models_covers_every_table() -> None:
    """Test that `_ordered_models` maps every table to a class.

    Guards against `SQLModel._sa_registry` (a private attribute) silently
    dropping tables after a SQLModel upgrade.
    """
    assert len(_ordered_models()) == len(SQLModel.metadata.tables)


def test__ordered_models_is_topologically_valid() -> None:
    """Test that every model's FK targets appear earlier in the returned order."""
    models = _ordered_models()
    position = {cls: i for i, cls in enumerate(models)}
    for cls in models:
        for _, target_cls in _fk_targets(cls):
            assert position[target_cls] < position[cls]
