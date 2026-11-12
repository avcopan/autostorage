"""Tests for SQLAlchemy ORM event listeners."""

import tempfile
import uuid
from collections.abc import Callable, Generator
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from autostorage import IdentityGenerationWarning
from autostorage.database import Database
from autostorage.models import (
    CalculationRow,
    GeometryRow,
    GeometryTrajectoryLink,
    IdentityRow,
    ModelRow,
    PropertyKindRow,
    PropertyValueRow,
    StageRow,
    StationaryPointRow,
    StepRow,
    TrajectoryRow,
)

# Test data constants
NDIM_2 = 2
NDIM_3 = 3
EXPECTED_IDENTITY_COUNT_THREE = 3
EXPECTED_IDENTITY_COUNT_SIX = 6
NATOMS_THREE = 3
NATOMS_TWO = 2


@pytest.fixture
def db_path() -> Generator[Path]:
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def database(db_path: Path) -> Generator[Database]:
    """Create a Database instance for testing."""
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def make_calculation() -> Callable[[], CalculationRow]:
    """Create factory for an optimization CalculationRow with its own ModelRow."""

    def _make() -> CalculationRow:
        return CalculationRow(
            model=ModelRow(program="psi4", method="B3LYP"), calc_type="opt"
        )

    return _make


@pytest.fixture
def make_geometry_methane() -> Callable[[], GeometryRow]:
    """Create factory for a methane geometry (C, H, H, H, H)."""

    def _make() -> GeometryRow:
        return GeometryRow(
            symbols=["C", "H", "H", "H", "H"],
            coordinates=[
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [-1.0, 0.0, 0.0],
            ],
            charge=0,
            spin=0,
        )

    return _make


@pytest.fixture
def make_geometry_water() -> Callable[[], GeometryRow]:
    """Create factory for a water geometry (O, H, H)."""

    def _make() -> GeometryRow:
        return GeometryRow(
            symbols=["O", "H", "H"],
            coordinates=[[0.0, 0.0, 0.0], [0.0, 0.76, 0.59], [0.0, -0.76, 0.59]],
        )

    return _make


class TestSortStepStageIds:
    """Tests for sort_step_stage_ids event listener."""

    def test_stage_ids_sorted_on_insert(self, database: Database) -> None:
        """stage_id1 and stage_id2 are auto-sorted on insert."""
        with database.session() as session:
            # Create two stages (stage1 gets smaller id)
            stage_small = StageRow(is_ts=False)
            stage_large = StageRow(is_ts=False)
            session.add_all([stage_small, stage_large])
            session.flush()

            # stage_large.id should be > stage_small.id
            assert stage_large.id is not None
            assert stage_small.id is not None
            assert stage_large.id > stage_small.id

            # Create step with reversed stage IDs (large first, then small)
            step = StepRow(
                stage_id1=stage_large.id,
                stage_id2=stage_small.id,
                is_barrierless=True,
            )
            session.add(step)
            session.flush()

            # Verify IDs were auto-sorted (should be small < large)
            assert step.stage_id1 is not None
            assert step.stage_id2 is not None
            assert step.stage_id1 < step.stage_id2
            assert step.stage_id1 == stage_small.id
            assert step.stage_id2 == stage_large.id

    def test_stage_ids_sorted_on_update(self, database: Database) -> None:
        """stage_id1 and stage_id2 are auto-sorted on update."""
        with database.session() as session:
            # Create three stages
            stage_a = StageRow(is_ts=False)
            stage_b = StageRow(is_ts=False)
            stage_c = StageRow(is_ts=False)
            session.add_all([stage_a, stage_b, stage_c])
            session.flush()

            # Ensure A < B < C
            assert stage_a.id is not None
            assert stage_b.id is not None
            assert stage_c.id is not None
            assert stage_a.id < stage_b.id < stage_c.id

            # Create step with correct order (A, B)
            step = StepRow(
                stage_id1=stage_a.id,
                stage_id2=stage_b.id,
                is_barrierless=True,
            )
            session.add(step)
            session.flush()

            # Update with reversed order (C, A) -> should become (A, C)
            step.stage_id1 = stage_c.id
            step.stage_id2 = stage_a.id
            session.flush()

            # Verify IDs were auto-sorted to (A, C)
            assert step.stage_id1 is not None
            assert step.stage_id2 is not None
            assert step.stage_id1 < step.stage_id2
            assert step.stage_id1 == stage_a.id
            assert step.stage_id2 == stage_c.id

    def test_equal_stage_ids_unchanged(self, database: Database) -> None:
        """If stage_id1 == stage_id2, they remain unchanged."""
        with database.session() as session:
            # Create a single stage
            stage = StageRow(is_ts=False)
            session.add(stage)
            session.flush()

            # Create step with equal IDs (will fail constraint but that's OK)
            step = StepRow(
                stage_id1=stage.id,
                stage_id2=stage.id,
                is_barrierless=True,
            )
            session.add(step)

            # The constraint check happens during commit
            with pytest.raises(IntegrityError):
                session.commit()

    def test_sorting_three_stage_ids(self, database: Database) -> None:
        """Sorting works with three different stages."""
        with database.session() as session:
            # Create three stages
            stage_x = StageRow(is_ts=False)
            stage_y = StageRow(is_ts=False)
            stage_z = StageRow(is_ts=False)
            session.add_all([stage_x, stage_y, stage_z])
            session.flush()

            # X < Y < Z
            assert stage_x.id is not None
            assert stage_y.id is not None
            assert stage_z.id is not None

            # Create step with reversed order (Z, X)
            step = StepRow(
                stage_id1=stage_z.id,
                stage_id2=stage_x.id,
                is_barrierless=True,
            )
            session.add(step)
            session.flush()

            # Verify they were sorted to (X, Z)
            assert step.stage_id1 is not None
            assert step.stage_id2 is not None
            assert step.stage_id1 < step.stage_id2
            assert step.stage_id1 == stage_x.id
            assert step.stage_id2 == stage_z.id


class TestVerifyStepBarrierlessConsistency:
    """Tests for verify_step_barrierless_consistency event listener."""

    def test_barrierless_requires_no_ts(self, database: Database) -> None:
        """Barrierless step (stage_id_ts=None) must have is_barrierless=True."""
        with database.session() as session:
            # Create two stages
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            session.add_all([stage1, stage2])
            session.flush()

            # Try to create barrierless step without is_barrierless=True
            step = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=None,
                is_barrierless=False,  # Invalid
            )
            session.add(step)

            with pytest.raises(ValueError, match="must have is_barrierless=True"):
                session.flush()

    def test_non_barrierless_requires_ts(self, database: Database) -> None:
        """Non-barrierless step must have stage_id_ts!=None."""
        with database.session() as session:
            # Create three stages (two regular, one TS)
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            session.add_all([stage1, stage2])
            session.flush()

            # Try to create non-barrierless step without transition state
            step = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=None,
                is_barrierless=False,
            )
            session.add(step)

            with pytest.raises(ValueError, match="must have is_barrierless=True"):
                session.flush()

    def test_barrierless_step_valid(self, database: Database) -> None:
        """Barrierless step with is_barrierless=True and stage_id_ts=None is valid."""
        with database.session() as session:
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            session.add_all([stage1, stage2])
            session.flush()

            step = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=None,
                is_barrierless=True,
            )
            session.add(step)
            session.flush()

            # Should succeed
            assert step.stage_id_ts is None
            assert step.is_barrierless is True

    def test_step_with_ts_valid(self, database: Database) -> None:
        """Step with transition state and is_barrierless=False is valid."""
        with database.session() as session:
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            stage_ts = StageRow(is_ts=True)
            session.add_all([stage1, stage2, stage_ts])
            session.flush()

            step = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=stage_ts.id,
                is_barrierless=False,
            )
            session.add(step)
            session.flush()

            # Should succeed
            assert step.stage_id_ts == stage_ts.id
            assert step.is_barrierless is False

    def test_step_with_ts_requires_is_barrierless_false(
        self, database: Database
    ) -> None:
        """Step with stage_id_ts!=None must have is_barrierless=False."""
        with database.session() as session:
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            stage_ts = StageRow(is_ts=True)
            session.add_all([stage1, stage2, stage_ts])
            session.flush()

            # Try to create step with TS but is_barrierless=True (invalid)
            step = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=stage_ts.id,
                is_barrierless=True,  # Invalid with TS present
            )
            session.add(step)

            with pytest.raises(ValueError, match="must have is_barrierless=False"):
                session.flush()

    def test_barrierless_consistency_on_update(self, database: Database) -> None:
        """Barrierless consistency is checked on update."""
        with database.session() as session:
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            session.add_all([stage1, stage2])
            session.flush()

            # Create a valid barrierless step
            step = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=None,
                is_barrierless=True,
            )
            session.add(step)
            session.flush()

            # Try to update to invalid state
            step.is_barrierless = False

            with pytest.raises(ValueError, match="must have is_barrierless=True"):
                session.flush()


class TestVerifyTrajectoryGeometryNdim:
    """Tests for verify_trajectory_geometry_ndim event listener."""

    def test_matching_index_and_ndim(
        self, database: Database, make_geometry_methane: Callable[[], GeometryRow]
    ) -> None:
        """Index length matching ndim is accepted."""
        with database.session() as session:
            geom = make_geometry_methane()
            traj = TrajectoryRow(ndim=NDIM_2)
            session.add_all([geom, traj])
            session.flush()

            link = GeometryTrajectoryLink(
                geometry_id=geom.id,
                trajectory_id=traj.id,
                index=[0, 1],  # length matches ndim
            )
            link.trajectory = traj
            session.add(link)
            session.flush()

            assert link.index == [0, 1]
            assert link.trajectory.ndim == NDIM_2

    def test_mismatched_index_and_ndim_raises(
        self, database: Database, make_geometry_methane: Callable[[], GeometryRow]
    ) -> None:
        """Index length not matching ndim raises ValueError."""
        with database.session() as session:
            geom = make_geometry_methane()
            traj = TrajectoryRow(ndim=NDIM_3)
            session.add_all([geom, traj])
            session.flush()

            link = GeometryTrajectoryLink(
                geometry_id=geom.id,
                trajectory_id=traj.id,
                index=[0, 1],  # length doesn't match ndim
            )
            link.trajectory = traj
            session.add(link)

            with pytest.raises(ValueError, match="does not match"):
                session.flush()

    def test_index_infers_ndim(
        self, database: Database, make_geometry_methane: Callable[[], GeometryRow]
    ) -> None:
        """Index length infers trajectory ndim if ndim is None."""
        with database.session() as session:
            geom = make_geometry_methane()
            traj = TrajectoryRow(ndim=None)
            session.add_all([geom, traj])
            session.flush()

            link = GeometryTrajectoryLink(
                geometry_id=geom.id,
                trajectory_id=traj.id,
                index=[0, 1, 2],  # length 3
            )
            link.trajectory = traj
            session.add(link)
            session.flush()

            assert link.trajectory.ndim == NDIM_3

    def test_missing_index_with_set_ndim_raises(
        self, database: Database, make_geometry_methane: Callable[[], GeometryRow]
    ) -> None:
        """Missing index when ndim is set raises ValueError."""
        with database.session() as session:
            geom = make_geometry_methane()
            traj = TrajectoryRow(ndim=NDIM_2)
            session.add_all([geom, traj])
            session.flush()

            link = GeometryTrajectoryLink(
                geometry_id=geom.id,
                trajectory_id=traj.id,
                index=None,  # Missing index
            )
            link.trajectory = traj
            session.add(link)

            with pytest.raises(ValueError, match="index is missing"):
                session.flush()

    def test_none_trajectory_skipped(self, database: Database) -> None:
        """Link with None trajectory is skipped gracefully."""
        with database.session() as session:
            link = GeometryTrajectoryLink(
                geometry_id=uuid.uuid4(),  # Will be invalid but event shouldn't crash
                trajectory_id=None,
                index=None,
            )
            session.add(link)

            # Event should handle None trajectory gracefully
            # (the insert will fail on FK constraint, but event shouldn't crash)

    def test_index_none_and_ndim_none(
        self, database: Database, make_geometry_methane: Callable[[], GeometryRow]
    ) -> None:
        """Both index and ndim None is allowed."""
        with database.session() as session:
            geom = make_geometry_methane()
            traj = TrajectoryRow(ndim=None)
            session.add_all([geom, traj])
            session.flush()

            link = GeometryTrajectoryLink(
                geometry_id=geom.id,
                trajectory_id=traj.id,
                index=None,
            )
            link.trajectory = traj
            session.add(link)
            session.flush()

            assert link.index is None
            assert link.trajectory.ndim is None

    def test_geometry_ndim_update(self, database: Database) -> None:
        """Trajectory ndim is updated on link insert if previously None."""
        with database.session() as session:
            geom = GeometryRow(
                symbols=["C"],
                coordinates=[[0.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            traj = TrajectoryRow(ndim=None)
            session.add_all([geom, traj])
            session.flush()

            # First link infers ndim
            link1 = GeometryTrajectoryLink(
                geometry_id=geom.id,
                trajectory_id=traj.id,
                index=[0, 1],
            )
            link1.trajectory = traj
            session.add(link1)
            session.flush()

            assert traj.ndim == NDIM_2

            # Second link with same trajectory and matching index works
            geom2 = GeometryRow(
                symbols=["C"],
                coordinates=[[1.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add(geom2)
            session.flush()

            link2 = GeometryTrajectoryLink(
                geometry_id=geom2.id,
                trajectory_id=traj.id,
                index=[1, 2],  # matches ndim
            )
            link2.trajectory = traj
            session.add(link2)
            session.flush()

            assert link2.index == [1, 2]


def _identity_for_algorithm(
    stat_point: StationaryPointRow, algorithm_name: str
) -> IdentityRow:
    """Return the single identity attached to `stat_point` for `algorithm_name`."""
    matches = [
        ident
        for ident in stat_point.identities
        if ident.algorithm.name == algorithm_name
    ]
    assert len(matches) == 1
    return matches[0]


class TestAddInchiIdentity:
    """Tests for add_inchi_identity event listener."""

    def test_inchi_identity_added_on_insert(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """InChI identity is automatically attached to a new stationary point."""
        with database.session() as session:
            calc = make_calculation()
            session.add(calc)
            session.flush()

            geom = make_geometry_methane()
            session.add(geom)
            session.flush()

            stat_point = StationaryPointRow(
                geometry_id=geom.id, calculation_id=calc.id, order=0
            )
            session.add(stat_point)
            session.flush()

            assert len(stat_point.identities) == EXPECTED_IDENTITY_COUNT_THREE
            identity = _identity_for_algorithm(stat_point, "rdkit_inchi")
            assert identity.algorithm.kind == "stereoisomer"
            assert identity.algorithm.name == "rdkit_inchi"
            assert identity.value.startswith("InChI=")

    def test_existing_inchi_identity_reused(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """Existing InChI identity is reused for duplicate geometries."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            # Create two identical geometries
            geom1 = make_geometry_methane()
            geom2 = make_geometry_methane()
            session.add_all([geom1, geom2])
            session.flush()

            stat1 = StationaryPointRow(
                geometry_id=geom1.id, calculation_id=calc1.id, order=0
            )
            stat2 = StationaryPointRow(
                geometry_id=geom2.id, calculation_id=calc2.id, order=0
            )
            session.add_all([stat1, stat2])
            session.flush()

            assert len(stat1.identities) == EXPECTED_IDENTITY_COUNT_THREE
            assert len(stat2.identities) == EXPECTED_IDENTITY_COUNT_THREE
            inchi1 = _identity_for_algorithm(stat1, "rdkit_inchi")
            inchi2 = _identity_for_algorithm(stat2, "rdkit_inchi")
            assert inchi1.id == inchi2.id
            assert inchi1.value == inchi2.value

            # Both stationary points share one identity per registered algorithm,
            # so there is only one IdentityRow per algorithm in total.
            identity_count = len(session.exec(select(IdentityRow)).all())
            assert identity_count == EXPECTED_IDENTITY_COUNT_THREE

    def test_different_geometries_create_different_identities(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """Different geometries create different InChI identities."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            geom1 = make_geometry_methane()
            geom2 = GeometryRow(
                symbols=["C", "C"],
                coordinates=[[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add_all([geom1, geom2])
            session.flush()

            stat1 = StationaryPointRow(
                geometry_id=geom1.id, calculation_id=calc1.id, order=0
            )
            stat2 = StationaryPointRow(
                geometry_id=geom2.id, calculation_id=calc2.id, order=0
            )
            session.add_all([stat1, stat2])
            session.flush()

            assert len(stat1.identities) == EXPECTED_IDENTITY_COUNT_THREE
            assert len(stat2.identities) == EXPECTED_IDENTITY_COUNT_THREE
            inchi1 = _identity_for_algorithm(stat1, "rdkit_inchi")
            inchi2 = _identity_for_algorithm(stat2, "rdkit_inchi")
            assert inchi1.id != inchi2.id
            assert inchi1.value != inchi2.value

            # Each stationary point has its own identity per registered
            # algorithm, none of which are shared.
            identity_count = len(session.exec(select(IdentityRow)).all())
            assert identity_count == EXPECTED_IDENTITY_COUNT_SIX

    def test_inchi_identity_added_with_relationship_object(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """InChI identity is added when StationaryPointRow uses relationship object."""
        with database.session() as session:
            calc = make_calculation()
            geom = make_geometry_methane()

            # Create StationaryPointRow with relationship objects (no IDs)
            # This mimics the pattern used in the demo where objects are created
            # and added together without intermediate flushes
            stat_point = StationaryPointRow(calculation=calc, geometry=geom, order=0)

            session.add_all([calc, geom, stat_point])
            session.flush()

            # Identity should be auto-populated despite using relationship objects
            assert len(stat_point.identities) == EXPECTED_IDENTITY_COUNT_THREE
            identity = _identity_for_algorithm(stat_point, "rdkit_inchi")
            assert identity.algorithm.kind == "stereoisomer"
            assert identity.algorithm.name == "rdkit_inchi"
            assert identity.value.startswith("InChI=")


class TestAddSmilesIdentity:
    """Tests for the SMILES identity attached by the registry identity listener."""

    def test_smiles_identity_added_on_insert(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """SMILES is automatically attached as an IdentityRow to stationary point."""
        with database.session() as session:
            calc = make_calculation()
            session.add(calc)
            session.flush()

            geom = make_geometry_methane()
            session.add(geom)
            session.flush()

            stat_point = StationaryPointRow(
                geometry_id=geom.id, calculation_id=calc.id, order=0
            )
            session.add(stat_point)
            session.flush()

            # Should have one identity per registered algorithm.
            assert len(stat_point.identities) == EXPECTED_IDENTITY_COUNT_THREE
            smiles_identity = _identity_for_algorithm(stat_point, "rdkit_smiles")
            assert smiles_identity.value == "C"  # Methane SMILES

    def test_duplicate_smiles_not_created(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """Duplicate SMILES are not created for the same geometry."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            # Create two identical geometries
            geom1 = make_geometry_methane()
            geom2 = make_geometry_methane()
            session.add_all([geom1, geom2])
            session.flush()

            stat1 = StationaryPointRow(
                geometry_id=geom1.id, calculation_id=calc1.id, order=0
            )
            stat2 = StationaryPointRow(
                geometry_id=geom2.id, calculation_id=calc2.id, order=0
            )
            session.add_all([stat1, stat2])
            session.flush()

            # Both stationary points should share the same SMILES identity row.
            smiles1 = _identity_for_algorithm(stat1, "rdkit_smiles")
            smiles2 = _identity_for_algorithm(stat2, "rdkit_smiles")
            assert smiles1.id == smiles2.id
            assert smiles1.value == "C"

            # Only one IdentityRow per registered algorithm, shared between both
            # stationary points.
            identity_count = len(session.exec(select(IdentityRow)).all())
            assert identity_count == EXPECTED_IDENTITY_COUNT_THREE

    def test_different_smiles_for_different_geometries(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """Different geometries create different SMILES identities."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            # Methane
            geom1 = make_geometry_methane()
            # Two carbons, no hydrogens
            geom2 = GeometryRow(
                symbols=["C", "C"],
                coordinates=[[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add_all([geom1, geom2])
            session.flush()

            stat1 = StationaryPointRow(
                geometry_id=geom1.id, calculation_id=calc1.id, order=0
            )
            stat2 = StationaryPointRow(
                geometry_id=geom2.id, calculation_id=calc2.id, order=0
            )
            session.add_all([stat1, stat2])
            session.flush()

            smiles1 = _identity_for_algorithm(stat1, "rdkit_smiles")
            smiles2 = _identity_for_algorithm(stat2, "rdkit_smiles")
            assert smiles1.id != smiles2.id
            assert smiles1.value == "C"
            # C2 SMILES should be different from methane
            assert smiles2.value != "C"


class TestAddHillIdentity:
    """Tests for the hill_formula identity attached by the identity listener."""

    def test_hill_identity_added_on_insert(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """hill_formula is automatically attached as an IdentityRow."""
        with database.session() as session:
            calc = make_calculation()
            session.add(calc)
            session.flush()

            geom = make_geometry_methane()
            session.add(geom)
            session.flush()

            stat_point = StationaryPointRow(
                geometry_id=geom.id, calculation_id=calc.id, order=0
            )
            session.add(stat_point)
            session.flush()

            # Should have one identity per registered algorithm.
            assert len(stat_point.identities) == EXPECTED_IDENTITY_COUNT_THREE
            hill_identity = _identity_for_algorithm(stat_point, "hill_formula")
            assert hill_identity.value == "CH4"  # Methane hill_formula

    def test_duplicate_hill_not_created(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """Duplicate hill_formulas are not created for the same geometry."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            # Create two identical geometries
            geom1 = make_geometry_methane()
            geom2 = make_geometry_methane()
            session.add_all([geom1, geom2])
            session.flush()

            stat1 = StationaryPointRow(
                geometry_id=geom1.id, calculation_id=calc1.id, order=0
            )
            stat2 = StationaryPointRow(
                geometry_id=geom2.id, calculation_id=calc2.id, order=0
            )
            session.add_all([stat1, stat2])
            session.flush()

            # Both stationary points should share the same hill_formula identity.
            hill1 = _identity_for_algorithm(stat1, "hill_formula")
            hill2 = _identity_for_algorithm(stat2, "hill_formula")
            assert hill1.id == hill2.id
            assert hill1.value == "CH4"

            # Only one IdentityRow per registered algorithm, shared between both
            # stationary points.
            identity_count = len(session.exec(select(IdentityRow)).all())
            assert identity_count == EXPECTED_IDENTITY_COUNT_THREE

    def test_different_hill_for_different_geometries(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
    ) -> None:
        """Different geometries create different hill_formula identities."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            # Methane
            geom1 = make_geometry_methane()
            # Two carbons, no hydrogens
            geom2 = GeometryRow(
                symbols=["C", "C"],
                coordinates=[[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add_all([geom1, geom2])
            session.flush()

            stat1 = StationaryPointRow(
                geometry_id=geom1.id, calculation_id=calc1.id, order=0
            )
            stat2 = StationaryPointRow(
                geometry_id=geom2.id, calculation_id=calc2.id, order=0
            )
            session.add_all([stat1, stat2])
            session.flush()

            hill1 = _identity_for_algorithm(stat1, "hill_formula")
            hill2 = _identity_for_algorithm(stat2, "hill_formula")
            assert hill1.id != hill2.id
            assert hill1.value == "CH4"
            # C2 hill_formula should be different from methane
            assert hill2.value != "CH4"


class TestVerifyPropertyValues:
    """Tests for verify_property_values_before_flush event listener."""

    def test_integer_energy_stored_as_float64(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Integer energies are accepted and stored at full precision."""
        with database.session() as session:
            pv = PropertyValueRow(
                geometry=make_geometry_water(),
                calculation=make_calculation(),
                property_kind_name="energy",
                value=-1234.567891234,
            )
            pv_int = PropertyValueRow(
                geometry=pv.geometry,
                calculation=pv.calculation,
                property_kind_name="energy",
                value=-1,
            )
            session.add_all([pv, pv_int])
            session.commit()
            session.refresh(pv)

            assert pv.value.dtype == np.float64
            assert float(pv.value) == -1234.567891234
            assert float(pv_int.value) == -1.0

    def test_gradient_accepts_flat_and_matrix_shapes(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Gradients may be flat ``(3N,)`` or ``(N, 3)``."""
        with database.session() as session:
            geo, calc = make_geometry_water(), make_calculation()
            for value in (np.zeros(9), np.zeros((3, 3))):
                session.add(
                    PropertyValueRow(
                        geometry=geo,
                        calculation=calc,
                        property_kind_name="gradient",
                        value=value,
                    )
                )
            session.commit()

    @pytest.mark.parametrize(
        ("kind", "value"),
        [
            ("energy", [1.0, 2.0]),
            ("gradient", np.zeros(6)),
            ("hessian", np.zeros((9, 6))),
            ("hessian", [[1.0], [1.0, 2.0]]),
        ],
    )
    def test_invalid_shape_raises(
        self,
        database: Database,
        kind: str,
        value: object,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Values with an invalid shape are rejected."""
        with database.session() as session:
            session.add(
                PropertyValueRow(
                    geometry=make_geometry_water(),
                    calculation=make_calculation(),
                    property_kind_name=kind,
                    value=value,
                )
            )
            with pytest.raises(ValueError, match="expected shape"):
                session.flush()

    def test_property_kind_loaded_from_database(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A `PropertyKindRow` loaded from the database validates values."""
        with database.session() as session:
            kind = session.get(PropertyKindRow, "energy")
            assert kind is not None
            session.add(
                PropertyValueRow(
                    geometry=make_geometry_water(),
                    calculation=make_calculation(),
                    property_kind=kind,
                    value=[1.0, 2.0],
                )
            )
            with pytest.raises(ValueError, match="expected shape"):
                session.flush()


class TestVerifyValidStationaryHasHessian:
    """Tests for verify_valid_stationary_has_hessian event listener."""

    def test_validated_without_hessian_raises(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A validated stationary point requires a Hessian."""
        with database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(),
                calculation=make_calculation(),
                is_validated=True,
            )
            session.add(stp)
            with pytest.raises(ValueError, match="without a Hessian"):
                session.flush()

    def test_validated_with_hessian(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A validated stationary point with a Hessian is accepted."""
        with database.session() as session:
            geo, calc = make_geometry_water(), make_calculation()
            hess = PropertyValueRow(
                geometry=geo,
                calculation=calc,
                property_kind_name="hessian",
                value=np.zeros((9, 9)),
            )
            stp = StationaryPointRow(geometry=geo, calculation=calc, is_validated=True)
            session.add_all([hess, stp])
            session.commit()

            assert stp.is_validated


class TestTrajectoryNdimPersisted:
    """The inferred trajectory ndim is written to the database."""

    def test_inferred_ndim_persisted(
        self, database: Database, make_geometry_water: Callable[[], GeometryRow]
    ) -> None:
        """`TrajectoryRow.ndim` inferred from a link index is persisted."""
        with database.session() as session:
            traj = TrajectoryRow()
            link = GeometryTrajectoryLink(
                geometry=make_geometry_water(), trajectory=traj, index=[0, 1]
            )
            session.add_all([traj, link])
            session.commit()
            traj_id = traj.id

        with database.session() as session:
            traj = session.get(TrajectoryRow, traj_id)
            assert traj is not None
            assert traj.ndim == NDIM_2


class TestIdentityGenerationFailures:
    """Identity algorithms that fail are skipped with a warning."""

    def test_metal_skips_unsupported_algorithms(
        self, database: Database, make_calculation: Callable[[], CalculationRow]
    ) -> None:
        """Metal-containing geometries are stored with only supported identities."""
        with database.session() as session:
            geo = GeometryRow(
                symbols=["Fe", "Cl", "Cl"],
                coordinates=[[0.0, 0.0, 0.0], [2.2, 0.0, 0.0], [-2.2, 0.0, 0.0]],
                spin=4,
            )
            stp = StationaryPointRow(geometry=geo, calculation=make_calculation())
            session.add(stp)
            with pytest.warns(IdentityGenerationWarning, match="metals"):
                session.commit()

            assert [(i.algorithm.name, i.value) for i in stp.identities] == [
                ("hill_formula", "Cl2Fe")
            ]

    def test_empty_identity_value_skipped(
        self, database: Database, make_calculation: Callable[[], CalculationRow]
    ) -> None:
        """Empty identity values are not stored."""
        with database.session() as session:
            geo = GeometryRow(
                symbols=["H", "H"], coordinates=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]]
            )
            stp = StationaryPointRow(geometry=geo, calculation=make_calculation())
            session.add(stp)
            with pytest.warns(IdentityGenerationWarning, match="empty identity"):
                session.commit()

            assert all(ident.value for ident in stp.identities)


class TestIdentitiesOnGeometryChange:
    """Identities are regenerated when a stationary point's geometry changes."""

    def test_reassigned_geometry_updates_identities(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Reassigning `geometry` replaces the stationary point's identities."""
        with database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()
            assert "H2O" in {i.value for i in stp.identities}

            stp.geometry = make_geometry_methane()
            session.commit()

            values = {i.value for i in stp.identities}
            assert "CH4" in values
            assert "H2O" not in values


class TestPendingSiblingIdentities:
    """Stationary points added in the same flush share their identities."""

    def test_same_flush_shares_identities(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Equivalent stationary points in one flush reuse the same identities."""
        with database.session() as session:
            calc = make_calculation()
            stp1 = StationaryPointRow(geometry=make_geometry_water(), calculation=calc)
            stp2 = StationaryPointRow(geometry=make_geometry_water(), calculation=calc)
            session.add_all([stp1, stp2])
            session.commit()

            assert {i.id for i in stp1.identities} == {i.id for i in stp2.identities}
            assert len(session.exec(select(IdentityRow)).all()) == (
                EXPECTED_IDENTITY_COUNT_THREE
            )


class TestListenerScope:
    """Listeners only apply to `AutostorageSession`s."""

    def test_plain_session_has_no_listeners(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A plain `sqlmodel.Session` does not attach identities."""
        with Session(database.engine) as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()

            assert stp.identities == []


class TestPersistedSiblingIdentities:
    """Child identities of persisted siblings are passed to algorithms."""

    def test_sibling_smiles_reused(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A new stationary point reuses its persisted sibling's SMILES."""
        with database.session() as session:
            calc = make_calculation()
            stp1 = StationaryPointRow(geometry=make_geometry_water(), calculation=calc)
            session.add(stp1)
            session.commit()

            # Replace the canonical SMILES with an equivalent, non-canonical one
            smiles = _identity_for_algorithm(stp1, "rdkit_smiles")
            stp1.identities.remove(smiles)
            stp1.identities.append(
                IdentityRow(algorithm_id=smiles.algorithm_id, value="[H]O[H]")
            )
            session.commit()

            stp2 = StationaryPointRow(geometry=make_geometry_water(), calculation=calc)
            session.add(stp2)
            session.commit()

            assert _identity_for_algorithm(stp2, "rdkit_smiles").value == "[H]O[H]"
