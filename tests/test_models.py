"""Models module tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.exc import IntegrityError

from autostorage.database import Database
from autostorage.models import (
    CalculationGeometryLink,
    CalculationRow,
    CalculationTrajectoryLink,
    EnergyRow,
    GeometryRow,
    GeometryTrajectoryLink,
    GradientRow,
    HessianRow,
    IdentityExtraRow,
    IdentityRow,
    IdentityStationaryLink,
    ModelRow,
    StageRow,
    StageStationaryLink,
    StationaryPointRow,
    StepRow,
    StepValidationLink,
    TrajectoryRow,
    ValidationRow,
)
from autostorage.types import Role


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


class TestGeometryRow:
    """Tests for GeometryRow model."""

    def test_create_geometry_with_list_coordinates(self, database: Database) -> None:
        """GeometryRow can be created with list coordinates."""
        with database.session() as session:
            geom = GeometryRow(
                symbols=["C", "H"],
                coordinates=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add(geom)
            session.commit()

            assert geom.id is not None
            assert isinstance(geom.coordinates, np.ndarray)
            assert geom.coordinates.shape == (2, 3)

    def test_create_geometry_with_numpy_coordinates(self, database: Database) -> None:
        """GeometryRow can be created with numpy array coordinates."""
        with database.session() as session:
            coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
            geom = GeometryRow(symbols=["C", "H"], coordinates=coords, charge=0, spin=0)
            session.add(geom)
            session.commit()

            assert geom.id is not None
            assert isinstance(geom.coordinates, np.ndarray)
            np.testing.assert_array_equal(geom.coordinates, coords)

    def test_geometry_symbols_stored_as_json(self, database: Database) -> None:
        """GeometryRow symbols are stored and retrieved correctly."""
        with database.session() as session:
            geom = GeometryRow(
                symbols=["C", "O", "H"],
                coordinates=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add(geom)
            session.commit()

            result = session.query(GeometryRow).filter_by(id=geom.id).first()
            assert result is not None
            assert result.symbols == ["C", "O", "H"]

    def test_geometry_charge_and_spin(self, database: Database) -> None:
        """GeometryRow stores charge and spin correctly."""
        with database.session() as session:
            geom = GeometryRow(
                symbols=["C"],
                coordinates=[[0.0, 0.0, 0.0]],
                charge=1,
                spin=1,
            )
            session.add(geom)
            session.commit()

            assert geom.charge == 1
            assert geom.spin == 1

    def test_geometry_relationships(self, database: Database) -> None:
        """GeometryRow relationships are initially empty."""
        with database.session() as session:
            geom = GeometryRow(
                symbols=["C"],
                coordinates=[[0.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add(geom)
            session.commit()

            assert geom.energies == []
            assert geom.gradients == []
            assert geom.hessians == []
            assert geom.stationary_points == []
            assert geom.trajectory_links == []
            assert geom.calculation_links == []


class TestTrajectoryRow:
    """Tests for TrajectoryRow model."""

    def test_create_trajectory_with_ndim(self, database: Database) -> None:
        """TrajectoryRow can be created with ndim specified."""
        with database.session() as session:
            traj = TrajectoryRow(ndim=3)
            session.add(traj)
            session.commit()

            assert traj.id is not None
            assert traj.ndim == 3  # noqa: PLR2004

    def test_create_trajectory_without_ndim(self, database: Database) -> None:
        """TrajectoryRow can be created without ndim."""
        with database.session() as session:
            traj = TrajectoryRow(ndim=None)
            session.add(traj)
            session.commit()

            assert traj.id is not None
            assert traj.ndim is None

    def test_trajectory_relationships(self, database: Database) -> None:
        """TrajectoryRow relationships are initially empty."""
        with database.session() as session:
            traj = TrajectoryRow(ndim=2)
            session.add(traj)
            session.commit()

            assert traj.geometry_links == []
            assert traj.calculation_links == []


class TestModelRow:
    """Tests for ModelRow model."""

    def test_create_model_minimal(self, database: Database) -> None:
        """ModelRow can be created with minimal required fields."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.commit()

            assert model.id is not None
            assert model.program == "psi4"
            assert model.method == "B3LYP"
            assert model.basis is None
            assert model.program_version is None
            assert model.keywords == {}

    def test_create_model_complete(self, database: Database) -> None:
        """ModelRow can be created with all fields specified."""
        with database.session() as session:
            model = ModelRow(
                program="orca",
                program_version="5.0.3",
                method="MP2",
                basis="cc-pvdz",
                keywords={"convergence": "tight", "scf_type": "df"},
            )
            session.add(model)
            session.commit()

            assert model.id is not None
            assert model.program_version == "5.0.3"
            assert model.basis == "cc-pvdz"
            assert model.keywords == {"convergence": "tight", "scf_type": "df"}

    def test_model_keywords_default_empty_dict(self, database: Database) -> None:
        """ModelRow keywords default to empty dict."""
        with database.session() as session:
            model = ModelRow(program="gaussian", method="HF")
            session.add(model)
            session.commit()

            assert model.keywords == {}


class TestCalculationRow:
    """Tests for CalculationRow model."""

    def test_create_calculation(self, database: Database) -> None:
        """CalculationRow can be created with a model reference."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(
                model_id=model.id,
                calc_type="energy",
                input_provenance={"source": "test"},
                output_provenance={"status": "success"},
            )
            session.add(calc)
            session.commit()

            assert calc.id is not None
            assert calc.model_id == model.id
            assert calc.calc_type == "energy"
            assert calc.input_provenance == {"source": "test"}
            assert calc.output_provenance == {"status": "success"}

    def test_calculation_relationships(self, database: Database) -> None:
        """CalculationRow relationships are initially empty."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="energy")
            session.add(calc)
            session.commit()

            assert calc.energies == []
            assert calc.gradients == []
            assert calc.hessians == []
            assert calc.validations == []
            assert calc.stationary_points == []
            assert calc.geometry_links == []
            assert calc.trajectory_links == []

    def test_calculation_model_relationship(self, database: Database) -> None:
        """CalculationRow.model relationship works correctly."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="energy")
            session.add(calc)
            session.commit()

            assert calc.model is not None
            assert calc.model.id == model.id
            assert calc.model.method == "B3LYP"

    def test_calculation_requires_model(self, database: Database) -> None:
        """CalculationRow requires a valid model_id."""
        with database.session() as session:
            calc = CalculationRow(model_id=9999, calc_type="energy")
            session.add(calc)

            with pytest.raises(IntegrityError):
                session.commit()


class TestResultRows:
    """Tests for result row models (Energy, Gradient, Hessian)."""

    def test_create_energy_row(self, database: Database) -> None:
        """EnergyRow can be created with geometry and calculation."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="energy")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            energy = EnergyRow(
                geometry_id=geom.id, calculation_id=calc.id, value=-37.8422
            )
            session.add(energy)
            session.commit()

            assert energy.id is not None
            assert energy.value == -37.8422  # noqa: PLR2004
            assert energy.geometry_id == geom.id
            assert energy.calculation_id == calc.id

    def test_create_gradient_row(self, database: Database) -> None:
        """GradientRow can be created with numpy array."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="gradient")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C", "H"],
                coordinates=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add(geom)
            session.flush()

            grad_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
            gradient = GradientRow(
                geometry_id=geom.id, calculation_id=calc.id, value=grad_value
            )
            session.add(gradient)
            session.commit()

            assert gradient.id is not None
            np.testing.assert_array_equal(gradient.value, grad_value)

    def test_create_hessian_row(self, database: Database) -> None:
        """HessianRow can be created with 2D numpy array."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="frequency")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"],
                coordinates=[[0.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add(geom)
            session.flush()

            hess_value = np.eye(3, dtype=np.float32)
            hessian = HessianRow(
                geometry_id=geom.id, calculation_id=calc.id, value=hess_value
            )
            session.add(hessian)
            session.commit()

            assert hessian.id is not None
            np.testing.assert_array_equal(hessian.value, hess_value)

    def test_result_relationships(self, database: Database) -> None:
        """Result rows have correct relationships to geometry and calculation."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="energy")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            energy = EnergyRow(
                geometry_id=geom.id, calculation_id=calc.id, value=-37.8422
            )
            session.add(energy)
            session.commit()

            assert energy.geometry is not None
            assert energy.geometry.id == geom.id
            assert energy.calculation is not None
            assert energy.calculation.id == calc.id


class TestValidationRow:
    """Tests for ValidationRow model."""

    def test_create_validation(self, database: Database) -> None:
        """ValidationRow can be created with calculation reference."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="irc")
            session.add(calc)
            session.flush()

            validation = ValidationRow(
                calculation_id=calc.id,
                method="irc",
                extras={"convergence": "tight"},
            )
            session.add(validation)
            session.commit()

            assert validation.id is not None
            assert validation.method == "irc"
            assert validation.extras == {"convergence": "tight"}

    def test_validation_extras_default(self, database: Database) -> None:
        """ValidationRow extras default to empty dict."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="irc")
            session.add(calc)
            session.flush()

            validation = ValidationRow(calculation_id=calc.id, method="irc")
            session.add(validation)
            session.commit()

            assert validation.extras == {}


class TestStationaryPointRow:
    """Tests for StationaryPointRow model."""

    def test_create_stationary_point(self, database: Database) -> None:
        """StationaryPointRow can be created with default values."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry_id=geom.id, calculation_id=calc.id)
            session.add(stat_pt)
            session.commit()

            assert stat_pt.id is not None
            assert stat_pt.order == 0
            assert stat_pt.is_pseudo is False
            assert stat_pt.is_validated is False

    def test_create_transition_state(self, database: Database) -> None:
        """StationaryPointRow can represent a transition state (order=1)."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt_ts")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            # Add Hessian to make stationary point valid
            rng = np.random.default_rng()
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=rng.random((3, 3), dtype=np.float32),
            )
            session.add(hessian)
            session.flush()

            stat_pt = StationaryPointRow(
                geometry_id=geom.id, calculation_id=calc.id, order=1, is_validated=True
            )
            session.add(stat_pt)
            session.commit()

            assert stat_pt.order == 1
            assert stat_pt.is_validated is True

    def test_stationary_point_relationships(self, database: Database) -> None:
        """StationaryPointRow relationships work correctly."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry_id=geom.id, calculation_id=calc.id)
            session.add(stat_pt)
            session.commit()

            assert stat_pt.geometry is not None
            assert stat_pt.geometry.id == geom.id
            assert stat_pt.calculation is not None
            assert stat_pt.calculation.id == calc.id
            # Note: auto-generated InChI identity from event listener
            assert len(stat_pt.identities) >= 1
            assert stat_pt.stages == []


class TestStageRow:
    """Tests for StageRow model."""

    def test_create_stage_non_ts(self, database: Database) -> None:
        """StageRow can be created as a non-TS stage."""
        with database.session() as session:
            stage = StageRow(is_ts=False)
            session.add(stage)
            session.commit()

            assert stage.id is not None
            assert stage.is_ts is False

    def test_create_stage_ts(self, database: Database) -> None:
        """StageRow can be created as a TS stage."""
        with database.session() as session:
            stage = StageRow(is_ts=True)
            session.add(stage)
            session.commit()

            assert stage.id is not None
            assert stage.is_ts is True

    def test_stage_relationships(self, database: Database) -> None:
        """StageRow relationships are initially empty."""
        with database.session() as session:
            stage = StageRow(is_ts=False)
            session.add(stage)
            session.commit()

            assert stage.stationaries == []
            assert stage.steps == []


class TestStepRow:
    """Tests for StepRow model."""

    def test_create_barrierless_step(self, database: Database) -> None:
        """StepRow can be created as a barrierless step."""
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
            session.commit()

            assert step.id is not None
            assert step.stage_id_ts is None
            assert step.is_barrierless is True

    def test_create_step_with_ts(self, database: Database) -> None:
        """StepRow can be created with a transition state."""
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
            session.commit()

            assert step.id is not None
            assert step.stage_id_ts == stage_ts.id
            assert step.is_barrierless is False

    def test_step_unique_constraint(self, database: Database) -> None:
        """StepRow enforces unique constraint on stage IDs."""
        with database.session() as session:
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            stage_ts = StageRow(is_ts=True)
            session.add_all([stage1, stage2, stage_ts])
            session.flush()

            step1 = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=stage_ts.id,
                is_barrierless=False,
            )
            session.add(step1)
            session.flush()

            # Try to create duplicate step
            step2 = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                stage_id_ts=stage_ts.id,
                is_barrierless=False,
            )
            session.add(step2)

            with pytest.raises(IntegrityError):
                session.commit()

    def test_step_stage_relationships(self, database: Database) -> None:
        """StepRow stage relationships work correctly."""
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
            session.commit()

            assert step.stage1 is not None
            assert step.stage1.id == stage1.id
            assert step.stage2 is not None
            assert step.stage2.id == stage2.id
            assert step.stage_ts is not None
            assert step.stage_ts.id == stage_ts.id


class TestIdentityRow:
    """Tests for IdentityRow model."""

    def test_create_identity(self, database: Database) -> None:
        """IdentityRow can be created with kind, algorithm, and value."""
        with database.session() as session:
            identity = IdentityRow(
                kind="stereoisomer",
                algorithm="rdkit inchi",
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity)
            session.commit()

            assert identity.id is not None
            assert identity.kind == "stereoisomer"
            assert identity.algorithm == "rdkit inchi"
            assert identity.value == "InChI=1S/CH4/h1H4"

    def test_identity_unique_constraint(self, database: Database) -> None:
        """IdentityRow enforces unique constraint on kind, algorithm, value."""
        with database.session() as session:
            identity1 = IdentityRow(
                kind="stereoisomer",
                algorithm="rdkit inchi",
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity1)
            session.flush()

            # Try to create duplicate identity
            identity2 = IdentityRow(
                kind="stereoisomer",
                algorithm="rdkit inchi",
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity2)

            with pytest.raises(IntegrityError):
                session.commit()

    def test_identity_relationships(self, database: Database) -> None:
        """IdentityRow relationships are initially empty."""
        with database.session() as session:
            identity = IdentityRow(
                kind="stereoisomer", algorithm="rdkit inchi", value="InChI=1S/CH4/h1H4"
            )
            session.add(identity)
            session.commit()

            assert identity.stationary_points == []
            assert identity.identity_extras == []


class TestIdentityExtraRow:
    """Tests for IdentityExtraRow model."""

    def test_create_identity_extra(self, database: Database) -> None:
        """IdentityExtraRow can be created with attribute and value."""
        with database.session() as session:
            identity = IdentityRow(
                kind="stereoisomer",
                algorithm="rdkit inchi",
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity)
            session.flush()

            extra = IdentityExtraRow(
                identity_id=identity.id,
                attribute="molecular_weight",
                value="16.04",
            )
            session.add(extra)
            session.commit()

            assert extra.id is not None
            assert extra.attribute == "molecular_weight"
            assert extra.value == "16.04"

    def test_identity_extra_relationship(self, database: Database) -> None:
        """IdentityExtraRow.identity relationship works correctly."""
        with database.session() as session:
            identity = IdentityRow(
                kind="stereoisomer", algorithm="rdkit inchi", value="InChI=1S/CH4/h1H4"
            )
            session.add(identity)
            session.flush()

            extra = IdentityExtraRow(
                identity_id=identity.id, attribute="molecular_weight", value="16.04"
            )
            session.add(extra)
            session.commit()

            assert extra.identity is not None
            assert extra.identity.id == identity.id
            assert extra.identity.value == "InChI=1S/CH4/h1H4"


class TestLinkModels:
    """Tests for link/association table models."""

    def test_calculation_geometry_link(self, database: Database) -> None:
        """CalculationGeometryLink can be created with role."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="energy")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            link = CalculationGeometryLink(
                calculation_id=calc.id, geometry_id=geom.id, role=Role.INPUT
            )
            session.add(link)
            session.commit()

            assert link.role == Role.INPUT
            assert link.geometry_id == geom.id
            assert link.calculation_id == calc.id

    def test_geometry_trajectory_link(self, database: Database) -> None:
        """GeometryTrajectoryLink can be created with index."""
        with database.session() as session:
            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            traj = TrajectoryRow(ndim=2)
            session.add_all([geom, traj])
            session.flush()

            link = GeometryTrajectoryLink(
                geometry_id=geom.id, trajectory_id=traj.id, index=[0, 0]
            )
            session.add(link)
            session.commit()

            assert link.index == [0, 0]

    def test_calculation_trajectory_link(self, database: Database) -> None:
        """CalculationTrajectoryLink can be created."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="irc")
            traj = TrajectoryRow(ndim=1)
            session.add_all([calc, traj])
            session.flush()

            link = CalculationTrajectoryLink(
                calculation_id=calc.id, trajectory_id=traj.id, role="output"
            )
            session.add(link)
            session.commit()

            assert link.role == "output"

    def test_stage_stationary_link(self, database: Database) -> None:
        """StageStationaryLink can be created."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry_id=geom.id, calculation_id=calc.id)
            stage = StageRow(is_ts=False)
            session.add_all([stat_pt, stage])
            session.flush()

            link = StageStationaryLink(stationary_id=stat_pt.id, stage_id=stage.id)
            session.add(link)
            session.commit()

            assert link.stationary_id == stat_pt.id
            assert link.stage_id == stage.id

    def test_step_validation_link(self, database: Database) -> None:
        """StepValidationLink can be created."""
        with database.session() as session:
            stage1 = StageRow(is_ts=False)
            stage2 = StageRow(is_ts=False)
            session.add_all([stage1, stage2])
            session.flush()

            step = StepRow(
                stage_id1=stage1.id,
                stage_id2=stage2.id,
                is_barrierless=True,
            )
            session.add(step)
            session.flush()

            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="irc")
            session.add(calc)
            session.flush()

            validation = ValidationRow(calculation_id=calc.id, method="irc")
            session.add(validation)
            session.flush()

            assert step.id is not None
            assert validation.id is not None
            link = StepValidationLink(step_id=step.id, validation_id=validation.id)
            session.add(link)
            session.commit()

            assert link.step_id == step.id
            assert link.validation_id == validation.id

    def test_identity_stationary_link(self, database: Database) -> None:
        """IdentityStationaryLink can be created."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry_id=geom.id, calculation_id=calc.id)
            identity = IdentityRow(
                kind="stereoisomer", algorithm="rdkit smiles", value="C"
            )
            session.add_all([stat_pt, identity])
            session.flush()

            assert stat_pt.id is not None
            assert identity.id is not None
            link = IdentityStationaryLink(
                stationary_id=stat_pt.id, identity_id=identity.id
            )
            session.add(link)
            session.commit()

            assert link.stationary_id == stat_pt.id
            assert link.identity_id == identity.id


class TestModelIntegration:
    """Integration tests for model interactions."""

    def test_geometry_with_multiple_results(self, database: Database) -> None:
        """Geometry can have multiple result types attached."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="frequency")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C", "H"],
                coordinates=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                charge=0,
                spin=0,
            )
            session.add(geom)
            session.flush()

            energy = EnergyRow(
                geometry_id=geom.id, calculation_id=calc.id, value=-37.8422
            )
            gradient = GradientRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]),
            )
            hessian = HessianRow(
                geometry_id=geom.id,
                calculation_id=calc.id,
                value=np.eye(6, dtype=np.float32),
            )
            session.add_all([energy, gradient, hessian])
            session.commit()

            assert len(geom.energies) == 1
            assert len(geom.gradients) == 1
            assert len(geom.hessians) == 1

    def test_calculation_with_multiple_geometries(self, database: Database) -> None:
        """Calculation can be linked to multiple geometries."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom1 = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            geom2 = GeometryRow(
                symbols=["C"], coordinates=[[0.1, 0.0, 0.0]], charge=0, spin=0
            )
            session.add_all([geom1, geom2])
            session.flush()

            link1 = CalculationGeometryLink(
                calculation_id=calc.id, geometry_id=geom1.id, role=Role.INPUT
            )
            link2 = CalculationGeometryLink(
                calculation_id=calc.id, geometry_id=geom2.id, role=Role.OUTPUT
            )
            session.add_all([link1, link2])
            session.commit()

            assert len(calc.geometry_links) == 2  # noqa: PLR2004

    def test_stationary_point_with_identity(self, database: Database) -> None:
        """Stationary point can be linked to an identity."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=0, spin=0
            )
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry_id=geom.id, calculation_id=calc.id)
            identity = IdentityRow(
                kind="stereoisomer", algorithm="rdkit smiles", value="C"
            )
            session.add_all([stat_pt, identity])
            session.flush()

            assert stat_pt.id is not None
            assert identity.id is not None
            link = IdentityStationaryLink(
                stationary_id=stat_pt.id, identity_id=identity.id
            )
            session.add(link)
            session.commit()

            # Test bidirectional relationship
            # Note: stat_pt will have auto-generated identities from event listener
            # plus the manually linked one
            assert len(stat_pt.identities) >= 2  # noqa: PLR2004
            assert identity.id in [i.id for i in stat_pt.identities]
            assert len(identity.stationary_points) == 1
            assert identity.stationary_points[0].id == stat_pt.id
