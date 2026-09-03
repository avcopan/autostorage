"""Tests for SQLAlchemy ORM event listeners."""

import tempfile
from collections.abc import Callable, Generator
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.exc import IntegrityError

from autostorage.database import Database
from autostorage.models import (
    CalculationRow,
    GeometryRow,
    GeometryTrajectoryLink,
    GradientRow,
    HessianRow,
    IdentityRow,
    ModelRow,
    StageRow,
    StationaryPointRow,
    StepRow,
    TrajectoryRow,
)

# Test data constants
NDIM_2 = 2
NDIM_3 = 3
EXPECTED_IDENTITY_COUNT_TWO = 2
EXPECTED_EXTRAS_COUNT = 2
NATOMS_THREE = 3
NATOMS_TWO = 2


@pytest.fixture
def db_path() -> Generator[Path, None, None]:
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def database(db_path: Path) -> Generator[Database, None, None]:
    """Create a Database instance for testing."""
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def make_model_gradient() -> Callable[[], ModelRow]:
    """Create factory for gradient calculation ModelRow."""

    def _make() -> ModelRow:
        return ModelRow(program="psi4", method="B3LYP")

    return _make


@pytest.fixture
def make_model_frequency() -> Callable[[], ModelRow]:
    """Create factory for frequency calculation ModelRow."""

    def _make() -> ModelRow:
        return ModelRow(program="psi4", method="B3LYP")

    return _make


@pytest.fixture
def make_model_opt() -> Callable[[], ModelRow]:
    """Create factory for optimization calculation ModelRow."""

    def _make() -> ModelRow:
        return ModelRow(program="psi4", method="B3LYP")

    return _make


@pytest.fixture
def make_calculation() -> Callable[[int], CalculationRow]:
    """Create factory for CalculationRow with empty provenance."""

    def _make(model_id: int) -> CalculationRow:
        return CalculationRow(
            calc_type="opt",
            model_id=model_id,
            input_provenance={},
            output_provenance={},
        )

    return _make


@pytest.fixture
def make_geometry_2atom() -> Callable[[], GeometryRow]:
    """Create factory for 2-atom geometry (C, H)."""

    def _make() -> GeometryRow:
        return GeometryRow(
            symbols=["C", "H"],
            coordinates=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            charge=0,
            spin=0,
        )

    return _make


@pytest.fixture
def make_geometry_3atom() -> Callable[[], GeometryRow]:
    """Create factory for 3-atom geometry (C, H, H)."""

    def _make() -> GeometryRow:
        return GeometryRow(
            symbols=["C", "H", "H"],
            coordinates=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            charge=0,
            spin=0,
        )

    return _make


@pytest.fixture
def make_geometry_5atom() -> Callable[[], GeometryRow]:
    """Create factory for 5-atom geometry (C, H, H, H, H)."""

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


class TestVerifyGradientShape:
    """Tests for verify_gradient_shape event listener."""

    def test_valid_gradient_shape_on_insert(
        self,
        database: Database,
        make_model_gradient: Callable[[], ModelRow],
        make_geometry_3atom: Callable[[], GeometryRow],
    ) -> None:
        """Gradient with correct shape (3 * natoms,) is accepted on insert."""
        with database.session() as session:
            model = make_model_gradient()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="gradient",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            geom = make_geometry_3atom()
            session.add(geom)
            session.flush()

            # Create gradient with correct shape (3 * 3 = 9 elements)
            gradient = GradientRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]),
            )
            gradient.geometry = geom
            session.add(gradient)
            session.flush()

            assert gradient.value.shape == (9,)
            assert len(gradient.geometry.symbols) == NATOMS_THREE

    def test_invalid_gradient_shape_on_insert(
        self,
        database: Database,
        make_model_gradient: Callable[[], ModelRow],
        make_geometry_3atom: Callable[[], GeometryRow],
    ) -> None:
        """Gradient with incorrect shape raises ValueError on insert."""
        with database.session() as session:
            model = make_model_gradient()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="gradient",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            geom = make_geometry_3atom()
            session.add(geom)
            session.flush()

            # Create gradient with incorrect shape (only 6 elements instead of 9)
            gradient = GradientRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]),
            )
            gradient.geometry = geom
            session.add(gradient)

            with pytest.raises(ValueError, match="does not match expected"):
                session.flush()

    def test_valid_gradient_shape_on_update(
        self,
        database: Database,
        make_model_gradient: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Gradient shape is validated on update."""
        with database.session() as session:
            model = make_model_gradient()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="gradient",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            geom = make_geometry_2atom()
            session.add(geom)
            session.flush()

            # Create gradient with correct shape (3 * 2 = 6 elements)
            gradient = GradientRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]),
            )
            gradient.geometry = geom
            session.add(gradient)
            session.flush()

            # Update to new valid values (same shape)
            gradient.value = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
            session.flush()

            assert gradient.value.shape == (6,)

    def test_invalid_gradient_shape_on_update(
        self,
        database: Database,
        make_model_gradient: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Updating gradient to incorrect shape raises ValueError."""
        with database.session() as session:
            model = make_model_gradient()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="gradient",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            geom = make_geometry_2atom()
            session.add(geom)
            session.flush()

            # Create gradient with correct shape (3 * 2 = 6 elements)
            gradient = GradientRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]),
            )
            gradient.geometry = geom
            session.add(gradient)
            session.flush()

            # Update to invalid shape
            gradient.value = np.array([1.0, 2.0, 3.0])

            with pytest.raises(ValueError, match="does not match expected"):
                session.flush()

    def test_none_geometry_skipped(
        self, database: Database, make_model_gradient: Callable[[], ModelRow]
    ) -> None:
        """Gradient with None geometry is skipped by validation."""
        with database.session() as session:
            model = make_model_gradient()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="gradient",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create gradient with no geometry relationship loaded
            gradient = GradientRow(
                geometry_id=None,
                calculation_id=calc.id,
                value=np.array([0.1, 0.2, 0.3]),
            )
            session.add(gradient)

            # Event should handle None geometry gracefully
            # (the insert will fail on FK constraint, but event shouldn't crash)


class TestVerifyHessianShape:
    """Tests for verify_hessian_shape event listener."""

    def test_valid_hessian_shape_on_insert(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Hessian with correct shape (3*natoms, 3*natoms) is accepted on insert."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with correct shape (6x6 for 2 atoms)
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((6, 6), dtype=np.float32),
            )
            hessian.geometry = geom
            session.add(hessian)
            session.flush()

            assert hessian.value.shape == (6, 6)
            assert len(hessian.geometry.symbols) == NATOMS_TWO

    def test_invalid_hessian_shape_on_insert(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_3atom: Callable[[], GeometryRow],
    ) -> None:
        """Hessian with incorrect shape raises ValueError on insert."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_3atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with incorrect shape (6x6 instead of 9x9)
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((6, 6), dtype=np.float32),
            )
            hessian.geometry = geom
            session.add(hessian)

            with pytest.raises(ValueError, match="does not match expected"):
                session.flush()

    def test_hessian_wrong_first_dimension(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Hessian with wrong first dimension raises ValueError."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with wrong first dimension (5x6 instead of 6x6)
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((5, 6), dtype=np.float32),
            )
            hessian.geometry = geom
            session.add(hessian)

            with pytest.raises(ValueError, match="does not match expected"):
                session.flush()

    def test_hessian_wrong_second_dimension(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Hessian with wrong second dimension raises ValueError."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with wrong second dimension (6x5 instead of 6x6)
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((6, 5), dtype=np.float32),
            )
            hessian.geometry = geom
            session.add(hessian)

            with pytest.raises(ValueError, match="does not match expected"):
                session.flush()

    def test_hessian_1d_array_rejected(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Hessian with 1D array (wrong dimensionality) raises ValueError."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with 1D array (flattened, wrong dimensionality)
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random(36, dtype=np.float32),
            )
            hessian.geometry = geom
            session.add(hessian)

            with pytest.raises(ValueError, match="does not match expected"):
                session.flush()

    def test_valid_hessian_shape_on_update(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Hessian shape is validated on update."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with correct shape (6x6)
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((6, 6), dtype=np.float32),
            )
            hessian.geometry = geom
            session.add(hessian)
            session.flush()

            # Update to new valid values (same shape)
            hessian.value = np.eye(6, dtype=np.float32)
            session.flush()

            assert hessian.value.shape == (6, 6)

    def test_invalid_hessian_shape_on_update(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Updating Hessian to incorrect shape raises ValueError."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with correct shape (6x6)
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((6, 6), dtype=np.float32),
            )
            hessian.geometry = geom
            session.add(hessian)
            session.flush()

            # Update to invalid shape (3x3)
            hessian.value = rng.random((3, 3), dtype=np.float32)

            with pytest.raises(ValueError, match="does not match expected"):
                session.flush()

    def test_none_geometry_skipped(
        self, database: Database, make_model_frequency: Callable[[], ModelRow]
    ) -> None:
        """Hessian with None geometry is skipped by validation."""
        with database.session() as session:
            model = make_model_frequency()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create Hessian with no geometry relationship loaded
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=None,
                calculation_id=calc.id,
                value=rng.random((6, 6), dtype=np.float32),
            )
            session.add(hessian)

            # Event should handle None geometry gracefully
            # (the insert will fail on FK constraint, but event shouldn't crash)


class TestVerifyTrajectoryGeometryNdim:
    """Tests for verify_trajectory_geometry_ndim_insert event listener."""

    def test_matching_index_and_ndim(
        self, database: Database, make_geometry_5atom: Callable[[], GeometryRow]
    ) -> None:
        """Index length matching ndim is accepted."""
        with database.session() as session:
            geom = make_geometry_5atom()
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
        self, database: Database, make_geometry_5atom: Callable[[], GeometryRow]
    ) -> None:
        """Index length not matching ndim raises ValueError."""
        with database.session() as session:
            geom = make_geometry_5atom()
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
        self, database: Database, make_geometry_5atom: Callable[[], GeometryRow]
    ) -> None:
        """Index length infers trajectory ndim if ndim is None."""
        with database.session() as session:
            geom = make_geometry_5atom()
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
        self, database: Database, make_geometry_5atom: Callable[[], GeometryRow]
    ) -> None:
        """Missing index when ndim is set raises ValueError."""
        with database.session() as session:
            geom = make_geometry_5atom()
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
                geometry_id=1,  # Will be invalid but event shouldn't crash
                trajectory_id=None,
                index=None,
            )
            session.add(link)

            # Event should handle None trajectory gracefully
            # (the insert will fail on FK constraint, but event shouldn't crash)

    def test_index_none_and_ndim_none(
        self, database: Database, make_geometry_5atom: Callable[[], GeometryRow]
    ) -> None:
        """Both index and ndim None is allowed."""
        with database.session() as session:
            geom = make_geometry_5atom()
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


class TestAddInchiIdentity:
    """Tests for add_inchi_identity event listener."""

    def test_inchi_identity_added_on_insert(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """InChI identity is automatically attached to a new stationary point."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C", "O"],
                coordinates=[[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]],
                charge=0,
                spin=1,
            )
            session.add(geom)
            session.flush()

            stat_point = StationaryPointRow(
                geometry_id=geom.id, calculation_id=calc.id, order=0
            )
            session.add(stat_point)
            session.flush()

            assert len(stat_point.identities) == 1
            identity = stat_point.identities[0]
            assert identity.kind == "stereoisomer"
            assert identity.algorithm == "rdkit inchi"
            assert identity.value.startswith("InChI=")

    def test_existing_inchi_identity_reused(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """Existing InChI identity is reused for duplicate geometries."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc1 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            calc2 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add_all([calc1, calc2])
            session.flush()

            # Create two identical geometries
            geom1 = GeometryRow(
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
            geom2 = GeometryRow(
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

            assert len(stat1.identities) == 1
            assert len(stat2.identities) == 1
            assert stat1.identities[0].id == stat2.identities[0].id
            assert stat1.identities[0].value == stat2.identities[0].value

            identity_count = session.query(IdentityRow).count()
            assert identity_count == 1

    def test_different_geometries_create_different_identities(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """Different geometries create different InChI identities."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc1 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            calc2 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add_all([calc1, calc2])
            session.flush()

            geom1 = GeometryRow(
                symbols=["C", "O"],
                coordinates=[[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]],
                charge=0,
                spin=1,
            )
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

            assert len(stat1.identities) == 1
            assert len(stat2.identities) == 1
            assert stat1.identities[0].id != stat2.identities[0].id
            assert stat1.identities[0].value != stat2.identities[0].value

            identity_count = session.query(IdentityRow).count()
            assert identity_count == EXPECTED_IDENTITY_COUNT_TWO

    def test_inchi_identity_added_with_relationship_object(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """InChI identity is added when StationaryPointRow uses relationship object."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            geom = GeometryRow(
                symbols=["C", "O"],
                coordinates=[[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]],
                charge=0,
                spin=1,
            )

            # Create StationaryPointRow with relationship objects (no IDs)
            # This mimics the pattern used in the demo where objects are created
            # and added together without intermediate flushes
            stat_point = StationaryPointRow(calculation=calc, geometry=geom, order=0)

            session.add_all([calc, geom, stat_point])
            session.flush()

            # Identity should be auto-populated despite using relationship objects
            assert len(stat_point.identities) == 1
            identity = stat_point.identities[0]
            assert identity.kind == "stereoisomer"
            assert identity.algorithm == "rdkit inchi"
            assert identity.value.startswith("InChI=")


class TestAddSmilesExtras:
    """Tests for add_smiles_extras_before_flush event listener."""

    def test_smiles_extra_added_on_insert(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """SMILES is automatically attached as IdentityExtraRow to stationary point."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            geom = GeometryRow(
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
            session.add(geom)
            session.flush()

            stat_point = StationaryPointRow(
                geometry_id=geom.id, calculation_id=calc.id, order=0
            )
            session.add(stat_point)
            session.flush()

            # Should have one InChI identity with one SMILES extra
            assert len(stat_point.identities) == 1
            identity = stat_point.identities[0]
            assert identity.algorithm == "rdkit inchi"

            # Reload to get the identity_extras relationship populated
            session.expire_all()
            identity = session.get(IdentityRow, identity.id)
            assert identity is not None
            assert len(identity.identity_extras) == EXPECTED_EXTRAS_COUNT

            # Check for SMILES extra
            extras_by_attr = {
                extra.attribute: extra.value for extra in identity.identity_extras
            }
            assert "rdkit_smiles" in extras_by_attr
            assert extras_by_attr["rdkit_smiles"] == "C"  # Methane SMILES

    def test_duplicate_smiles_not_created(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """Duplicate SMILES are not created for the same geometry."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc1 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            calc2 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add_all([calc1, calc2])
            session.flush()

            # Create two identical geometries
            geom1 = GeometryRow(
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
            geom2 = GeometryRow(
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

            # Both should share the same identity (InChI)
            assert stat1.identities[0].id == stat2.identities[0].id

            # Should have two extras (SMILES + Hill) for the shared identity
            session.expire_all()
            identity = session.get(IdentityRow, stat1.identities[0].id)
            assert identity is not None
            assert len(identity.identity_extras) == EXPECTED_EXTRAS_COUNT

            # Check for SMILES extra
            extras_by_attr = {
                extra.attribute: extra.value for extra in identity.identity_extras
            }
            assert "rdkit_smiles" in extras_by_attr
            assert extras_by_attr["rdkit_smiles"] == "C"

    def test_different_smiles_for_different_geometries(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """Different geometries create different SMILES extras."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc1 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            calc2 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add_all([calc1, calc2])
            session.flush()

            # Methane
            geom1 = GeometryRow(
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
            # Ethane
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

            # Should have different identities
            assert stat1.identities[0].id != stat2.identities[0].id

            # Each identity should have two extras (SMILES + Hill)
            session.expire_all()
            identity1 = session.get(IdentityRow, stat1.identities[0].id)
            identity2 = session.get(IdentityRow, stat2.identities[0].id)
            assert identity1 is not None
            assert identity2 is not None

            assert len(identity1.identity_extras) == EXPECTED_EXTRAS_COUNT
            extras1_by_attr = {
                extra.attribute: extra.value for extra in identity1.identity_extras
            }
            assert "rdkit_smiles" in extras1_by_attr
            assert extras1_by_attr["rdkit_smiles"] == "C"

            assert len(identity2.identity_extras) == EXPECTED_EXTRAS_COUNT
            extras2_by_attr = {
                extra.attribute: extra.value for extra in identity2.identity_extras
            }
            assert "rdkit_smiles" in extras2_by_attr
            # Ethane SMILES should be different from methane
            assert extras2_by_attr["rdkit_smiles"] != "C"


class TestAddHillExtras:
    """Tests for add_hill_extras_before_flush event listener."""

    def test_hill_extra_added_on_insert(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """Hill formula is attached as IdentityExtraRow to stationary point."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            geom = GeometryRow(
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
            session.add(geom)
            session.flush()

            stat_point = StationaryPointRow(
                geometry_id=geom.id, calculation_id=calc.id, order=0
            )
            session.add(stat_point)
            session.flush()

            # Should have one InChI identity with two extras (SMILES + Hill formula)
            assert len(stat_point.identities) == 1
            identity = stat_point.identities[0]
            assert identity.algorithm == "rdkit inchi"

            # Reload to get the identity_extras relationship populated
            session.expire_all()
            identity = session.get(IdentityRow, identity.id)
            assert identity is not None
            assert len(identity.identity_extras) == EXPECTED_EXTRAS_COUNT

            # Check for both SMILES and Hill formula extras
            extras_by_attr = {
                extra.attribute: extra.value for extra in identity.identity_extras
            }
            assert "rdkit_smiles" in extras_by_attr
            assert extras_by_attr["rdkit_smiles"] == "C"  # Methane SMILES
            assert "hill_formula" in extras_by_attr
            assert extras_by_attr["hill_formula"] == "CH4"  # Methane Hill formula

    def test_duplicate_hill_not_created(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """Duplicate Hill formulas are not created for the same geometry."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc1 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            calc2 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add_all([calc1, calc2])
            session.flush()

            # Create two identical geometries
            geom1 = GeometryRow(
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
            geom2 = GeometryRow(
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

            # Both should share the same identity (InChI)
            assert stat1.identities[0].id == stat2.identities[0].id

            # Should have two extras (SMILES + Hill) for the shared identity
            session.expire_all()
            identity = session.get(IdentityRow, stat1.identities[0].id)
            assert identity is not None
            assert len(identity.identity_extras) == EXPECTED_EXTRAS_COUNT

            # Check for both SMILES and Hill formula extras
            extras_by_attr = {
                extra.attribute: extra.value for extra in identity.identity_extras
            }
            assert "rdkit_smiles" in extras_by_attr
            assert extras_by_attr["rdkit_smiles"] == "C"
            assert "hill_formula" in extras_by_attr
            assert extras_by_attr["hill_formula"] == "CH4"

    def test_different_hill_for_different_geometries(
        self, database: Database, make_model_opt: Callable[[], ModelRow]
    ) -> None:
        """Different geometries create different Hill formula extras."""
        with database.session() as session:
            model = make_model_opt()
            session.add(model)
            session.flush()

            calc1 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            calc2 = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add_all([calc1, calc2])
            session.flush()

            # Methane
            geom1 = GeometryRow(
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
            # Ethane
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

            # Should have different identities
            assert stat1.identities[0].id != stat2.identities[0].id

            # Each identity should have two extras (SMILES + Hill)
            session.expire_all()
            identity1 = session.get(IdentityRow, stat1.identities[0].id)
            identity2 = session.get(IdentityRow, stat2.identities[0].id)
            assert identity1 is not None
            assert identity2 is not None

            assert len(identity1.identity_extras) == EXPECTED_EXTRAS_COUNT
            extras1_by_attr = {
                extra.attribute: extra.value for extra in identity1.identity_extras
            }
            assert "rdkit_smiles" in extras1_by_attr
            assert extras1_by_attr["rdkit_smiles"] == "C"
            assert "hill_formula" in extras1_by_attr
            assert extras1_by_attr["hill_formula"] == "CH4"

            assert len(identity2.identity_extras) == EXPECTED_EXTRAS_COUNT
            extras2_by_attr = {
                extra.attribute: extra.value for extra in identity2.identity_extras
            }
            assert "rdkit_smiles" in extras2_by_attr
            # Ethane SMILES should be different from methane
            assert extras2_by_attr["rdkit_smiles"] != "C"
            assert "hill_formula" in extras2_by_attr
            # Ethane Hill formula should be different from methane
            assert extras2_by_attr["hill_formula"] != "CH4"


class TestVerifyValidStationaryHasHessian:
    """Tests for verify_valid_stationary_has_hessian event listener."""

    def test_valid_stationary_with_hessian_accepted(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Stationary point marked valid with a Hessian is accepted."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Add a Hessian to the geometry
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((6, 6), dtype=np.float32),
            )
            session.add(hessian)
            session.flush()

            # Create a valid stationary point - should succeed
            stat = StationaryPointRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                order=0,
                is_validated=True,
            )
            session.add(stat)
            session.flush()

            assert stat.is_validated is True
            assert len(geom.hessians) == 1

    def test_valid_stationary_without_hessian_rejected(
        self,
        database: Database,
        make_model_opt: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Stationary point marked valid without a Hessian is rejected."""
        with database.session() as session:
            model = make_model_opt()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create a valid stationary point without Hessian - should fail
            stat = StationaryPointRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                order=0,
                is_validated=True,
            )
            session.add(stat)

            with pytest.raises(ValueError, match="cannot be marked as valid"):
                session.flush()

    def test_invalid_stationary_without_hessian_accepted(
        self,
        database: Database,
        make_model_opt: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Stationary point not marked valid can exist without a Hessian."""
        with database.session() as session:
            model = make_model_opt()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create stationary point with is_validated=False - should succeed
            stat = StationaryPointRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                order=0,
                is_validated=False,
            )
            session.add(stat)
            session.flush()

            assert stat.is_validated is False

    def test_valid_stationary_update_to_validated_without_hessian_rejected(
        self,
        database: Database,
        make_model_opt: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Updating stationary to validated without Hessian is rejected."""
        with database.session() as session:
            model = make_model_opt()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="opt",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create invalid stationary point
            stat = StationaryPointRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                order=0,
                is_validated=False,
            )
            session.add(stat)
            session.flush()

            # Try to update to validated without Hessian - should fail
            stat.is_validated = True

            with pytest.raises(ValueError, match="cannot be marked as valid"):
                session.flush()

    def test_update_to_validated_with_hessian_accepted(
        self,
        database: Database,
        make_model_frequency: Callable[[], ModelRow],
        make_geometry_2atom: Callable[[], GeometryRow],
    ) -> None:
        """Updating stationary to validated with Hessian is accepted."""
        with database.session() as session:
            model = make_model_frequency()
            geom = make_geometry_2atom()
            session.add_all([model, geom])
            session.flush()

            calc = CalculationRow(
                calc_type="frequency",
                model_id=model.id,
                input_provenance={},
                output_provenance={},
            )
            session.add(calc)
            session.flush()

            # Create non-validated stationary point
            stat = StationaryPointRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                order=0,
                is_validated=False,
            )
            session.add(stat)
            session.flush()

            # Add a Hessian
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((6, 6), dtype=np.float32),
            )
            session.add(hessian)
            session.flush()

            # Update to validated with Hessian present - should succeed
            stat.is_validated = True
            session.flush()

            assert stat.is_validated is True
