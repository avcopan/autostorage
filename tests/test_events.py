"""Tests for SQLAlchemy ORM event listeners."""

import itertools
import tempfile
import uuid
from collections.abc import Callable, Generator, Mapping
from pathlib import Path
from typing import Any

import autogeom
import numpy as np
import protomol
import pytest
from autogeom import Geometry, ureg
from protomol import AnyGraph
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from autostorage import (
    IdentityAlgorithmRegistry,
    IdentityGenerationWarning,
    IdentityKind,
    IdentityResult,
    ModelHashAlgorithm,
    ModelHashAlgorithmRegistry,
    ModelHashGenerationWarning,
    ModelHashKind,
    ModelHashProtocol,
    StationaryOrderWarning,
    events,
)
from autostorage.database import Database
from autostorage.events import MAX_MODEL_HASH_LENGTH
from autostorage.identity import protomol_graph
from autostorage.models import (
    CalculationRow,
    GeometryRow,
    GeometryTrajectoryLink,
    IdentityRow,
    IdentityStationaryLink,
    ModelHashLink,
    ModelHashRow,
    ModelRow,
    PropertyKindRow,
    PropertyValueRow,
    StageRow,
    StageStationaryLink,
    StationaryPointRow,
    StepRow,
    TrajectoryRow,
    geometry_hash,
    stage_hash,
)

# Test data constants
NDIM_2 = 2
NDIM_3 = 3
NON_GRAPH_IDENTITY_COUNT = 4
"""The built-in identities of a minimum that don't use its graph."""
KIND_GRAPH_EXCLUDED_COUNT = NON_GRAPH_IDENTITY_COUNT + 1
"""The built-in identities of a minimum (`smg_conn@1` included, the interim
`protomol_graph@0` is for saddle points only)."""
EXPECTED_IDENTITY_COUNT = KIND_GRAPH_EXCLUDED_COUNT
NATOMS_THREE = 3
NATOMS_TWO = 2
N_BUILTIN_HASHES = 2  # minimal@1 and exact@1


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


def _geometry_factory(
    symbols: list[str], coordinates: list[list[float]]
) -> Callable[[], GeometryRow]:
    """Return a factory for the geometry, translated further along x on each call.

    Stored geometries must be distinct, and translating keeps their identities.
    """
    calls = itertools.count()

    def _make() -> GeometryRow:
        shift = 0.01 * next(calls)
        coords = [[x + shift, y, z] for x, y, z in coordinates]
        return GeometryRow(symbols=symbols, coordinates=coords, charge=0, spin=0)

    return _make


@pytest.fixture
def make_geometry_water() -> Callable[[], GeometryRow]:
    """Create factory for a water geometry (O, H, H)."""
    return _geometry_factory(
        ["O", "H", "H"], [[0.0, 0.0, 0.0], [0.0, 0.76, 0.59], [0.0, -0.76, 0.59]]
    )


@pytest.fixture
def make_geometry_methane() -> Callable[[], GeometryRow]:
    """Create factory for a methane geometry (C, H, H, H, H)."""
    return _geometry_factory(
        ["C", "H", "H", "H", "H"],
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [-1.0, 0.0, 0.0],
        ],
    )


@pytest.fixture
def make_geometry_trans_difluoroethene() -> Callable[[], GeometryRow]:
    """Create factory for a planar trans-1,2-difluoroethene sketch (C2H2F2)."""
    return _geometry_factory(
        ["C", "C", "F", "H", "F", "H"],
        [
            [-0.6, 0.0, 0.0],
            [0.6, 0.0, 0.0],
            [-1.2, 1.0, 0.0],
            [-1.2, -1.0, 0.0],
            [1.2, -1.0, 0.0],
            [1.2, 1.0, 0.0],
        ],
    )


@pytest.fixture
def make_geometry_cis_difluoroethene() -> Callable[[], GeometryRow]:
    """Create factory for a planar cis-1,2-difluoroethene sketch (C2H2F2)."""
    return _geometry_factory(
        ["C", "C", "F", "H", "F", "H"],
        [
            [-0.6, 0.0, 0.0],
            [0.6, 0.0, 0.0],
            [-1.2, 1.0, 0.0],
            [-1.2, -1.0, 0.0],
            [1.2, 1.0, 0.0],
            [1.2, -1.0, 0.0],
        ],
    )


class TestSetGeometryHash:
    """Tests for set_geometry_hash event listener."""

    def test_hash_set_on_insert(
        self,
        database: Database,
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """The hash is set on insert and matches `geometry_hash`."""
        with database.session() as session:
            geo = make_geometry_water()
            session.add(geo)
            session.commit()
            session.refresh(geo)

            assert geo.hash == geometry_hash(geo)

    def test_duplicate_geometry_rejected(self, database: Database) -> None:
        """Storing an equal geometry again violates the unique hash."""
        coords = [[0.0, 0.0, 0.0], [0.0, 0.76, 0.59], [0.0, -0.76, 0.59]]
        with database.session() as session:
            session.add(GeometryRow(symbols=["O", "H", "H"], coordinates=coords))
            session.commit()

            session.add(GeometryRow(symbols=["O", "H", "H"], coordinates=coords))
            with pytest.raises(IntegrityError, match=r"geometry\.hash"):
                session.commit()

    @pytest.mark.parametrize(
        "changes",
        [
            {"symbols": ["S", "H", "H"]},
            {"charge": 2},
            {"coordinates": [[1e-12, 0.0, 0.0], [0.0, 0.76, 0.59], [0.0, -0.76, 0.59]]},
        ],
    )
    def test_different_geometries_allowed(
        self, database: Database, changes: dict[str, Any]
    ) -> None:
        """Geometries differing in any field get different hashes."""
        fields: dict[str, Any] = {
            "symbols": ["O", "H", "H"],
            "coordinates": [[0.0, 0.0, 0.0], [0.0, 0.76, 0.59], [0.0, -0.76, 0.59]],
        }
        geo1 = GeometryRow(**fields)
        geo2 = GeometryRow(**(fields | changes))
        with database.session() as session:
            session.add_all([geo1, geo2])
            session.commit()

            assert geo1.hash != geo2.hash

    def test_negative_zero_equals_zero(self) -> None:
        """-0.0 and 0.0 coordinates hash the same, as they compare equal."""
        geo1 = GeometryRow(symbols=["He"], coordinates=[[0.0, 0.0, 0.0]])
        geo2 = GeometryRow(symbols=["He"], coordinates=[[-0.0, 0.0, 0.0]])
        assert geometry_hash(geo1) == geometry_hash(geo2)

    def test_hash_updated(
        self,
        database: Database,
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """The hash is recomputed when the geometry changes."""
        with database.session() as session:
            geo = make_geometry_water()
            session.add(geo)
            session.commit()
            old_hash = geo.hash

            geo.coordinates = geo.coordinates + 1.0
            session.commit()
            session.refresh(geo)

            assert geo.hash != old_hash
            assert geo.hash == geometry_hash(geo)

    def test_lookup_by_hash(
        self,
        database: Database,
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A stored geometry can be found from an equal in-memory geometry."""
        geo = make_geometry_water()
        with database.session() as session:
            session.add(geo)
            session.commit()
            copy = geo.relabel_atoms([0, 1, 2])

            found = session.exec(
                select(GeometryRow).where(GeometryRow.hash == geometry_hash(copy))
            ).one()

            assert found.id == geo.id


class TestSetStageHash:
    """Tests for set_stage_hash_before_flush and stage_hash."""

    def test_hash_ignores_order_and_counts_repeats(self) -> None:
        """The hash ignores point order, but not counts or `is_ts`."""
        a, b = uuid.uuid4(), uuid.uuid4()
        value = stage_hash([(a, 2), (b, 1)], is_ts=False)
        assert stage_hash([(b, 1), (a, 2)], is_ts=False) == value
        assert stage_hash([(a, 1), (b, 1)], is_ts=False) != value
        assert stage_hash([(a, 2), (b, 1)], is_ts=True) != value

    def test_hash_set_on_flush(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """A new stage's hash is set from its points and counts."""
        a, b = make_point(), make_point()
        with database.session() as session:
            stage = StageRow.from_points([a, b, a])
            session.add(stage)
            session.flush()
            assert stage.hash == stage_hash([(a.id, 2), (b.id, 1)], is_ts=False)

    def test_duplicate_stage_raises(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """A second stage with the same content, built by hand, is rejected."""
        a = make_point()
        with database.session() as session:
            session.add(StageRow.from_points([a]))
            session.commit()

            session.add(StageRow.from_points([a]))
            with pytest.raises(IntegrityError):
                session.commit()

    @pytest.mark.parametrize("change", ["add", "remove", "recount", "is_ts"])
    def test_changing_links_rehashes(
        self,
        make_point: Callable[..., StationaryPointRow],
        database: Database,
        change: str,
    ) -> None:
        """Adding, removing, or recounting a link, or changing `is_ts`, rehashes."""
        a, b = make_point(), make_point()
        with database.session() as session:
            stage = StageRow.from_points([a, b])
            session.add(stage)
            session.commit()

            if change == "add":
                c = make_point()
                stage.stationary_links.append(StageStationaryLink(stationary=c))
                expected = [(a.id, 1), (b.id, 1), (c.id, 1)]
            elif change == "remove":
                b.stage_links.clear()
                expected = [(a.id, 1)]
            elif change == "recount":
                stage.stationary_links[0].count = 2
                link_a, link_b = stage.stationary_links
                expected = [(link_a.point_id, 2), (link_b.point_id, 1)]
            else:
                b.stage_links.clear()
                stage.is_ts = True
                expected = [(a.id, 1)]
            session.commit()

            is_ts = change == "is_ts"
            assert stage.hash == stage_hash(expected, is_ts=is_ts)

    def test_deleting_point_keeps_hash(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """Deleting a point leaves its stages' hashes as they were."""
        a, b = make_point(), make_point()
        with database.session() as session:
            stage = StageRow.from_points([a, b])
            session.add(stage)
            session.commit()
            value = stage.hash

            session.delete(b)
            session.commit()
            assert stage.hash == value


class TestSortStepStageIds:
    """Tests for sort_step_stage_ids event listener."""

    def test_stage_ids_sorted_on_insert(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """stage_id1 and stage_id2 are auto-sorted on insert."""
        with database.session() as session:
            # Create two stages, named by the order of their ids
            stages = [make_stage() for _ in range(2)]
            session.add_all(stages)
            session.flush()
            stage_small, stage_large = sorted(stages, key=lambda s: str(s.id))

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

    def test_stage_ids_sorted_on_update(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """stage_id1 and stage_id2 are auto-sorted on update."""
        with database.session() as session:
            # Create three stages, named so that A < B < C
            stages = [make_stage() for _ in range(3)]
            session.add_all(stages)
            session.flush()
            stage_a, stage_b, stage_c = sorted(stages, key=lambda s: str(s.id))

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

    def test_equal_stage_ids_unchanged(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """If stage_id1 == stage_id2, they remain unchanged."""
        with database.session() as session:
            # Create a single stage
            stage = make_stage()
            session.add(stage)
            session.flush()

            # Equal IDs are allowed: a self-reaction
            step = StepRow(
                stage_id1=stage.id,
                stage_id2=stage.id,
                is_barrierless=True,
            )
            session.add(step)
            session.commit()

            assert step.stage_id1 == step.stage_id2 == stage.id

    def test_sorting_three_stage_ids(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """Sorting works with three different stages."""
        with database.session() as session:
            # Create three stages, named so that X < Y < Z
            stages = [make_stage() for _ in range(3)]
            session.add_all(stages)
            session.flush()
            stage_x, _, stage_z = sorted(stages, key=lambda s: str(s.id))

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

    def test_barrierless_requires_no_ts(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """Barrierless step (stage_id_ts=None) must have is_barrierless=True."""
        with database.session() as session:
            # Create two stages
            stage1 = make_stage()
            stage2 = make_stage()
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

    def test_non_barrierless_requires_ts(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """Non-barrierless step must have stage_id_ts!=None."""
        with database.session() as session:
            # Create three stages (two regular, one TS)
            stage1 = make_stage()
            stage2 = make_stage()
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

    def test_barrierless_step_valid(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """Barrierless step with is_barrierless=True and stage_id_ts=None is valid."""
        with database.session() as session:
            stage1 = make_stage()
            stage2 = make_stage()
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

    def test_step_with_ts_valid(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """Step with transition state and is_barrierless=False is valid."""
        with database.session() as session:
            stage1 = make_stage()
            stage2 = make_stage()
            stage_ts = make_stage(is_ts=True)
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
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """Step with stage_id_ts!=None must have is_barrierless=False."""
        with database.session() as session:
            stage1 = make_stage()
            stage2 = make_stage()
            stage_ts = make_stage(is_ts=True)
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

    def test_barrierless_consistency_on_update(
        self, make_stage: Callable[..., StageRow], database: Database
    ) -> None:
        """Barrierless consistency is checked on update."""
        with database.session() as session:
            stage1 = make_stage()
            stage2 = make_stage()
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


class TestVerifyStepBalance:
    """Tests for verify_step_balance_before_flush."""

    def test_balanced_step_passes(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """A -> B with the same atoms and charge passes, with or without a TS."""
        with database.session() as session:
            step = StepRow(
                stage1=StageRow.from_points([make_point()]),
                stage2=StageRow.from_points([make_point()]),
                stage_ts=StageRow.from_points([make_point(order=1)], is_ts=True),
            )
            session.add(step)
            session.commit()

    def test_self_reaction_step(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """A -> A through a TS (both sides one stage) flushes and balances."""
        with database.session() as session:
            stage = StageRow.from_points([make_point()])
            step = StepRow(
                stage1=stage,
                stage2=stage,
                stage_ts=StageRow.from_points([make_point(order=1)], is_ts=True),
            )
            session.add(step)
            session.commit()
            assert step.stage_id1 == step.stage_id2 == stage.id

    def test_counts_are_weighted(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """A + A -> A2 passes, since the count of A is 2."""
        h_atom = make_point(["H"], spin=1)
        with database.session() as session:
            step = StepRow(
                stage1=StageRow.from_points([h_atom, h_atom]),
                stage2=StageRow.from_points([make_point()]),
                is_barrierless=True,
            )
            session.add(step)
            session.commit()

    @pytest.mark.parametrize(
        ("kwargs", "diff"),
        [
            ({"symbols": ["H", "H", "H"], "spin": 1}, "H: [+-]1"),
            ({"charge": 1, "spin": 1}, "charge: [+-]1"),
        ],
    )
    def test_unbalanced_step_raises(
        self,
        make_point: Callable[..., StationaryPointRow],
        database: Database,
        kwargs: dict[str, Any],
        diff: str,
    ) -> None:
        """A missing atom or a charge mismatch raises, naming the difference."""
        with database.session() as session:
            step = StepRow(
                stage1=StageRow.from_points([make_point()]),
                stage2=StageRow.from_points([make_point(**kwargs)]),
                is_barrierless=True,
            )
            session.add(step)
            with pytest.raises(ValueError, match=f"StepRow {step.id} .*{diff}"):
                session.flush()

    def test_unbalanced_ts_raises(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """A TS stage with different atoms raises."""
        with database.session() as session:
            step = StepRow(
                stage1=StageRow.from_points([make_point()]),
                stage2=StageRow.from_points([make_point()]),
                stage_ts=StageRow.from_points(
                    [make_point(["H", "H", "H"], spin=1, order=1)], is_ts=True
                ),
            )
            session.add(step)
            with pytest.raises(ValueError, match="stage_ts differs from stage1"):
                session.flush()

    def test_spin_change_passes(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """A spin-forbidden step (singlet -> triplet) passes."""
        with database.session() as session:
            step = StepRow(
                stage1=StageRow.from_points([make_point()]),
                stage2=StageRow.from_points([make_point(spin=2)]),
                is_barrierless=True,
            )
            session.add(step)
            session.commit()

    def test_changing_a_stage_rechecks_its_steps(
        self, make_point: Callable[..., StationaryPointRow], database: Database
    ) -> None:
        """Adding a point to a stored step's stage unbalances the step."""
        with database.session() as session:
            stage1 = StageRow.from_points([make_point()])
            step = StepRow(
                stage1=stage1,
                stage2=StageRow.from_points([make_point()]),
                is_barrierless=True,
            )
            session.add(step)
            session.commit()

            stage1.stationary_links[0].count = 2
            with pytest.raises(ValueError, match="unbalanced"):
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


def _identities(stat_point: StationaryPointRow) -> list[IdentityRow]:
    """Return the identities linked to `stat_point`."""
    return [link.identity for link in stat_point.identity_links]


def _link_for_algorithm(
    stat_point: StationaryPointRow, algorithm_name: str
) -> IdentityStationaryLink:
    """Return the single identity link of `stat_point` for `algorithm_name`."""
    matches = [
        link
        for link in stat_point.identity_links
        if link.identity.algorithm_name == algorithm_name
    ]
    assert len(matches) == 1
    return matches[0]


def _identity_for_algorithm(
    stat_point: StationaryPointRow, algorithm_name: str
) -> IdentityRow:
    """Return the single identity attached to `stat_point` for `algorithm_name`."""
    return _link_for_algorithm(stat_point, algorithm_name).identity


class TestAddInchiConnIdentity:
    """Test connectivity identities added by event listener."""

    def test_inchi_conn_identity_added_on_insert(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_cis_difluoroethene: Callable[[], GeometryRow],
        make_geometry_trans_difluoroethene: Callable[[], GeometryRow],
    ) -> None:
        """InChI identity is automatically attached to a new stationary point."""
        with database.session() as session:
            calc = make_calculation()
            session.add(calc)
            session.flush()

            geom1 = make_geometry_cis_difluoroethene()
            geom2 = make_geometry_trans_difluoroethene()
            session.add_all([geom1, geom2])
            session.flush()

            stat_point1 = StationaryPointRow(
                geometry_id=geom1.id, calculation_id=calc.id, order=0
            )
            stat_point2 = StationaryPointRow(
                geometry_id=geom2.id, calculation_id=calc.id, order=0
            )
            session.add_all([stat_point1, stat_point2])
            session.flush()

            # Stereo identities should be distinct
            identity_stereo1 = _identity_for_algorithm(stat_point1, "rdkit_inchi")
            identity_stereo2 = _identity_for_algorithm(stat_point2, "rdkit_inchi")
            assert identity_stereo1.id != identity_stereo2.id
            assert identity_stereo1.value == "InChI=1S/C2H2F2/c3-1-2-4/h1-2H/b2-1-"
            assert identity_stereo2.value == "InChI=1S/C2H2F2/c3-1-2-4/h1-2H/b2-1+"

            # Connectivity identities should match
            identity_conn1 = _identity_for_algorithm(stat_point1, "rdkit_inchi_conn")
            identity_conn2 = _identity_for_algorithm(stat_point2, "rdkit_inchi_conn")
            assert identity_conn1.id == identity_conn2.id
            assert identity_conn1.algorithm.kind == "isomer"
            assert identity_conn1.value == "InChI=1S/C2H2F2/c3-1-2-4/h1-2H"


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

            assert len(_identities(stat_point)) == EXPECTED_IDENTITY_COUNT
            identity = _identity_for_algorithm(stat_point, "rdkit_inchi")
            assert identity.algorithm.kind == "stereoisomer"
            assert identity.algorithm.name == "rdkit_inchi"
            assert identity.value == "InChI=1S/CH4/h1H4"

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

            assert len(_identities(stat1)) == EXPECTED_IDENTITY_COUNT
            assert len(_identities(stat2)) == EXPECTED_IDENTITY_COUNT
            inchi1 = _identity_for_algorithm(stat1, "rdkit_inchi")
            inchi2 = _identity_for_algorithm(stat2, "rdkit_inchi")
            assert inchi1.id == inchi2.id
            assert inchi1.value == "InChI=1S/CH4/h1H4"

            # Both stationary points share one identity per registered algorithm,
            # so there is only one IdentityRow per algorithm in total.
            identity_count = len(session.exec(select(IdentityRow)).all())
            assert identity_count == EXPECTED_IDENTITY_COUNT

    def test_different_geometries_create_different_identities(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Different geometries create different InChI identities."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            geom1 = make_geometry_methane()
            geom2 = make_geometry_water()
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

            assert len(_identities(stat1)) == EXPECTED_IDENTITY_COUNT
            assert len(_identities(stat2)) == EXPECTED_IDENTITY_COUNT
            inchi1 = _identity_for_algorithm(stat1, "rdkit_inchi")
            inchi2 = _identity_for_algorithm(stat2, "rdkit_inchi")
            assert inchi1.id != inchi2.id
            assert inchi1.value == "InChI=1S/CH4/h1H4"
            assert inchi2.value == "InChI=1S/H2O/h1H2"

            # Each stationary point has its own identity per registered
            # algorithm, none of which are shared.
            identity_count = len(session.exec(select(IdentityRow)).all())
            assert identity_count == 2 * EXPECTED_IDENTITY_COUNT

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
            assert len(_identities(stat_point)) == EXPECTED_IDENTITY_COUNT
            identity = _identity_for_algorithm(stat_point, "rdkit_inchi")
            assert identity.algorithm.kind == "stereoisomer"
            assert identity.algorithm.name == "rdkit_inchi"
            assert identity.value == "InChI=1S/CH4/h1H4"


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
            assert len(_identities(stat_point)) == EXPECTED_IDENTITY_COUNT
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
            assert identity_count == EXPECTED_IDENTITY_COUNT

    def test_different_smiles_for_different_geometries(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Different geometries create different SMILES identities."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            geom1 = make_geometry_methane()
            geom2 = make_geometry_water()
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
            assert smiles2.value == "O"


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
            assert len(_identities(stat_point)) == EXPECTED_IDENTITY_COUNT
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
            assert identity_count == EXPECTED_IDENTITY_COUNT

    def test_different_hill_for_different_geometries(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_methane: Callable[[], GeometryRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Different geometries create different hill_formula identities."""
        with database.session() as session:
            calc1, calc2 = make_calculation(), make_calculation()
            session.add_all([calc1, calc2])
            session.flush()

            geom1 = make_geometry_methane()
            geom2 = make_geometry_water()
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
            assert hill2.value == "H2O"


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
            with pytest.raises(ValueError, match=r"expected shape|numeric array"):
                session.flush()

    def test_quantity_converted_to_native_units(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Quantities are stored as magnitudes in the kind's native units."""
        with database.session() as session:
            geo, calc = make_geometry_water(), make_calculation()
            energy = PropertyValueRow(
                geometry=geo,
                calculation=calc,
                property_kind_name="energy",
                value=ureg.Quantity(-627.5094740631, "kcal/mol"),
            )
            gradient = PropertyValueRow(
                geometry=geo,
                calculation=calc,
                property_kind_name="gradient",
                value=ureg.Quantity(np.ones(9), "hartree / angstrom"),
            )
            session.add_all([energy, gradient])
            session.commit()
            session.expire_all()

            assert float(energy.value) == pytest.approx(-1.0)
            bohr_per_angstrom = ureg.Quantity(1, "bohr").m_as("angstrom")
            np.testing.assert_allclose(gradient.value, bohr_per_angstrom)

    def test_incompatible_units_raise(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Quantities with units of the wrong dimensionality are rejected."""
        with database.session() as session:
            session.add(
                PropertyValueRow(
                    geometry=make_geometry_water(),
                    calculation=make_calculation(),
                    property_kind_name="energy",
                    value=ureg.Quantity(1.0, "angstrom"),
                )
            )
            with pytest.raises(ValueError, match="compatible with 'hartree'"):
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


def _diatomic_hessian(k: float) -> np.ndarray:
    """Return a diatomic stretch Hessian; a negative `k` gives order 1."""
    hess = np.zeros((6, 6))
    hess[2, 2] = hess[5, 5] = k
    hess[2, 5] = hess[5, 2] = -k
    return hess


class TestValidateStationaryOrder:
    """Tests for validate_stationary_order_before_flush event listener."""

    @staticmethod
    def _add_point(
        session: Session, *ks: float, order: int = 0, is_pseudo: bool = False
    ) -> StationaryPointRow:
        """Add an HF stationary point with a Hessian for each force constant."""
        geo = GeometryRow(symbols=["H", "F"], coordinates=[[0, 0, 0], [0, 0, 0.92]])
        calc = CalculationRow(
            model=ModelRow(program="psi4", method="HF"), calc_type="freq"
        )
        session.add_all(
            PropertyValueRow(
                geometry=geo,
                calculation=calc,
                property_kind_name="hessian",
                value=_diatomic_hessian(k),
            )
            for k in ks
        )
        stp = StationaryPointRow(
            geometry=geo, calculation=calc, order=order, is_pseudo=is_pseudo
        )
        session.add(stp)
        return stp

    @pytest.mark.parametrize(("k", "order"), [(0.37, 0), (-0.1, 1)])
    def test_matching_order_validated(
        self, database: Database, k: float, order: int
    ) -> None:
        """A point whose Hessian has its order is validated."""
        with database.session() as session:
            stp = self._add_point(session, k, order=order)
            session.commit()
            assert stp.is_validated

    @pytest.mark.parametrize("ks", [(-0.1,), (0.37, -0.1), (np.nan,)])
    def test_mismatched_order_warns(
        self, database: Database, ks: tuple[float, ...]
    ) -> None:
        """A point is not validated unless every Hessian is valid and has its order."""
        with database.session() as session:
            stp = self._add_point(session, *ks)
            with pytest.warns(StationaryOrderWarning, match="has order 0"):
                session.commit()
            assert not stp.is_validated

    def test_pseudo_skipped(self, database: Database) -> None:
        """Pseudo stationary points are not validated."""
        with database.session() as session:
            stp = self._add_point(session, -0.1, is_pseudo=True)
            session.commit()
            assert not stp.is_validated

    def test_hessian_added_later_validates(self, database: Database) -> None:
        """Adding a Hessian to a stored point's geometry validates it."""
        with database.session() as session:
            stp = self._add_point(session)
            session.commit()
            assert not stp.is_validated

            session.add(
                PropertyValueRow(
                    geometry=stp.geometry,
                    calculation=stp.calculation,
                    property_kind_name="hessian",
                    value=_diatomic_hessian(0.37),
                )
            )
            session.commit()
            assert stp.is_validated

    def test_order_change_demotes(self, database: Database) -> None:
        """Changing `order` so it no longer matches resets `is_validated`."""
        with database.session() as session:
            stp = self._add_point(session, 0.37)
            session.commit()

            stp.order = 1
            with pytest.warns(StationaryOrderWarning, match="have orders \\[0\\]"):
                session.commit()
            assert not stp.is_validated

    def test_hessian_deleted_demotes(self, database: Database) -> None:
        """Deleting the only Hessian resets `is_validated`."""
        with database.session() as session:
            stp = self._add_point(session, 0.37)
            session.commit()

            session.delete(stp.geometry.properties[0])
            session.commit()
            assert not stp.is_validated


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

            assert [(i.algorithm.name, i.value) for i in _identities(stp)] == [
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

            assert all(ident.value for ident in _identities(stp))


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
            assert "H2O" in {i.value for i in _identities(stp)}

            stp.geometry = make_geometry_methane()
            session.commit()

            values = {i.value for i in _identities(stp)}
            assert "CH4" in values
            assert "H2O" not in values

    def test_reassigned_geometry_discards_algorithm_cache(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Relinking the same identities after a geometry change resets the cache."""
        with database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()
            ids_before = {ident.id for ident in _identities(stp)}
            for link in stp.identity_links:
                link.algorithm_cache = {"stale": True}
            session.commit()

            stp.geometry = make_geometry_water()
            session.commit()
            session.expire_all()

            assert {ident.id for ident in _identities(stp)} == ids_before
            assert all(link.algorithm_cache is None for link in stp.identity_links)


class TestOrderRestrictedIdentities:
    """Algorithms restricted to order 0 skip saddle points."""

    def test_transition_state_skips_inchi(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A first-order saddle point gets only its formula identity."""
        with database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation(), order=1
            )
            session.add(stp)
            session.commit()

            names = {i.algorithm.name for i in _identities(stp)}
            assert names == {"hill_formula"}

    def test_order_change_regenerates_identities(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """Changing `order` adds or removes the order-restricted identities.

        The graph identity stays: the graph is kept on an order change.
        """
        with database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()
            assert "rdkit_inchi" in {i.algorithm.name for i in _identities(stp)}

            stp.order = 1
            session.commit()
            names = {i.algorithm.name for i in _identities(stp)}
            assert names == {"hill_formula"}

            stp.order = 0
            session.commit()
            assert len(_identities(stp)) == EXPECTED_IDENTITY_COUNT


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

            assert {i.id for i in _identities(stp1)} == {
                i.id for i in _identities(stp2)
            }
            assert len(session.exec(select(IdentityRow)).all()) == (
                EXPECTED_IDENTITY_COUNT
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

            assert stp.identity_links == []


def _atom_count_graph_identity_fn(
    geo: Geometry,  # noqa: ARG001
    gra: AnyGraph | None = None,
    other_geos: Mapping[str, Geometry] | None = None,  # noqa: ARG001
) -> str:
    """A fake graph identity: the graph's atom count."""
    assert gra is not None
    return str(len(gra.symbols))


@pytest.fixture
def graph_database(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Database]:
    """A database with two graph algorithms for minima, besides `protomol_graph@0`.

    `min_graph@0` stands in for the stored graph of a minimum (`smg_low_t@1`, to come);
    `protomol_graph@0` is for saddle points only.
    """
    monkeypatch.setattr(
        IdentityAlgorithmRegistry,
        "algorithms",
        list(IdentityAlgorithmRegistry.algorithms),
    )
    IdentityAlgorithmRegistry.register(
        name="min_graph@0",
        kind=IdentityKind.GRAPH,
        identity_fn=protomol_graph.identity_fn,
        orders={0},
        stores_graph=True,
    )
    IdentityAlgorithmRegistry.register(
        name="atom_count_graph",
        kind=IdentityKind.GRAPH,
        identity_fn=_atom_count_graph_identity_fn,
        uses_graph=True,
    )
    with Database(db_path) as db:
        yield db


@pytest.fixture
def count_perceptions(monkeypatch: pytest.MonkeyPatch) -> list[Geometry]:
    """Record the geometries whose graph the listener perceives."""
    calls: list[Geometry] = []

    def _from_geometry(geo: Geometry) -> protomol.StereoMolGraph:
        calls.append(geo)
        return protomol.from_geometry(geo)

    monkeypatch.setattr(events, "from_geometry", _from_geometry)
    return calls


def _graph_identity_names(stp: StationaryPointRow) -> set[str]:
    """The names of the graph identities of `stp`."""
    return {i.algorithm.name for i in _identities(stp) if i.algorithm.kind == "graph"}


def _builtin_values(stp: StationaryPointRow) -> dict[str, str]:
    """The built-in identity values of `stp`, by algorithm name."""
    return {
        i.algorithm.name: i.value
        for i in _identities(stp)
        if i.algorithm.kind != "graph"
    }


class TestGraphIdentities:
    """Graph identities read the given or perceived graph."""

    def test_given_graph(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        count_perceptions: list[Geometry],
    ) -> None:
        """A point given a graph gets graph identities of that graph."""
        gra = protomol.examples.species()
        geo = GeometryRow(**protomol.embed(gra).model_dump())
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=geo, calculation=make_calculation(), graph=gra
            )
            assert stp.graph is gra
            session.add(stp)
            session.commit()

            link = _link_for_algorithm(stp, "min_graph@0")
            assert link.identity.value == protomol.canonical_json(gra)
            assert link.atom_map is not None
            canonical = protomol.from_json(link.identity.value)
            inverse = np.argsort(link.atom_map).tolist()
            assert protomol.relabel(canonical, inverse) == gra  # ty: ignore[invalid-argument-type]
            count = _identity_for_algorithm(stp, "atom_count_graph").value
            assert count == str(len(gra.symbols))
            assert count_perceptions == []

    def test_order0_perceives_graph_once(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
        count_perceptions: list[Geometry],
    ) -> None:
        """A minimum without a graph gets the perceived one, perceived once."""
        geo = make_geometry_water()
        with graph_database.session() as session:
            stp = StationaryPointRow(geometry=geo, calculation=make_calculation())
            session.add(stp)
            session.commit()

            value = _identity_for_algorithm(stp, "min_graph@0").value
            assert value == protomol.canonical_json(protomol.from_geometry(geo))
            assert _identity_for_algorithm(stp, "atom_count_graph").value == "3"
            assert len(count_perceptions) == 1
            assert stp.graph == protomol.from_geometry(geo)

    def test_order1_without_graph_skips(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
        count_perceptions: list[Geometry],
    ) -> None:
        """A saddle point without a graph gets no graph identities."""
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation(), order=1
            )
            session.add(stp)
            session.commit()

            assert _graph_identity_names(stp) == set()
            assert {i.algorithm.name for i in _identities(stp)} == {"hill_formula"}
            assert count_perceptions == []

    def test_order1_with_reaction_graph(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
    ) -> None:
        """A saddle point given a reaction graph gets graph identities."""
        ts_gra = protomol.examples.abstraction_ts()
        geo = GeometryRow(**protomol.embed(protomol.reactants(ts_gra)).model_dump())
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=geo, calculation=make_calculation(), order=1, graph=ts_gra
            )
            session.add(stp)
            session.commit()

            value = _identity_for_algorithm(stp, "protomol_graph@0").value
            assert value == protomol.canonical_json(ts_gra)

    def test_ts_and_reverse_share_identities_and_graph(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
    ) -> None:
        """A TS and its reverse get one `smg_conn@1` and one `protomol_graph@0`."""
        ts_gra = protomol.examples.abstraction_ts()
        rev = protomol.reverse(ts_gra)
        geo = protomol.embed(protomol.reactants(ts_gra))
        with graph_database.session() as session:
            fwd = StationaryPointRow(
                geometry=GeometryRow(**geo.model_dump()),
                calculation=make_calculation(),
                order=1,
                graph=ts_gra,
            )
            bwd = StationaryPointRow(
                geometry=GeometryRow(**autogeom.translate(geo, [1, 0, 0]).model_dump()),
                calculation=make_calculation(),
                order=1,
                graph=rev,
            )
            session.add_all([fwd, bwd])
            session.commit()

            for name in ("smg_conn@1", "protomol_graph@0"):
                assert (
                    _identity_for_algorithm(fwd, name).id
                    == _identity_for_algorithm(bwd, name).id
                )
            # The stored graph is the stereo-aware one, in each point's own direction
            assert set(fwd.stored_graphs()) == {"protomol_graph@0"}
            assert fwd.graph == ts_gra
            assert bwd.graph == rev
            cache = _link_for_algorithm(fwd, "protomol_graph@0").algorithm_cache
            assert cache is not None
            assert "reversed" in cache

    def test_builtins_unchanged(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
    ) -> None:
        """The built-in identities are the same with or without a graph."""
        gra = protomol.examples.species()
        geo = protomol.embed(gra)
        with graph_database.session() as session:
            with_graph = StationaryPointRow(
                geometry=GeometryRow(**geo.model_dump()),
                calculation=make_calculation(),
                graph=gra,
            )
            session.add(with_graph)
            session.commit()
            without = StationaryPointRow(
                geometry=GeometryRow(**autogeom.translate(geo, [1, 0, 0]).model_dump()),
                calculation=make_calculation(),
            )
            session.add(without)
            session.commit()

            assert len(_builtin_values(with_graph)) == KIND_GRAPH_EXCLUDED_COUNT
            assert _builtin_values(with_graph) == _builtin_values(without)

    def test_smg_conn_on_perceived_minimum(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A perceived minimum gets `smg_conn@1`, which stores no graph."""
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()

            gra = protomol.from_geometry(stp.geometry)
            expected = protomol.canonical_json(protomol.without_stereo(gra))
            assert _identity_for_algorithm(stp, "smg_conn@1").value == expected
            assert _link_for_algorithm(stp, "smg_conn@1").atom_map is not None
            assert set(stp.stored_graphs()) == {"min_graph@0"}
            assert "protomol_graph@0" not in {
                i.algorithm.name for i in _identities(stp)
            }

    def test_perception_failure_warns(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If no graph can be perceived, the graph identities are skipped."""

        def _fail(geo: Geometry) -> protomol.StereoMolGraph:  # noqa: ARG001
            msg = "no Lewis structure"
            raise protomol.GraphError(msg)

        monkeypatch.setattr(events, "from_geometry", _fail)
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            with pytest.warns(IdentityGenerationWarning, match="no graph perceived"):
                session.commit()

            assert _graph_identity_names(stp) == set()
            assert len(_identities(stp)) == NON_GRAPH_IDENTITY_COUNT

    def test_preferred_stored_graph_by_kind(
        self,
        db_path: Path,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With several `stores_graph` links, the kind decides, before the name."""
        monkeypatch.setattr(
            IdentityAlgorithmRegistry,
            "algorithms",
            list(IdentityAlgorithmRegistry.algorithms),
        )

        def _bondless_fn(
            geo: Geometry,  # noqa: ARG001
            gra: AnyGraph | None = None,
            other_geos: Mapping[str, Geometry] | None = None,  # noqa: ARG001
        ) -> IdentityResult:
            assert gra is not None
            bare = protomol.StereoMolGraph(symbols=gra.symbols, bonds=[])
            canonical, atom_map = protomol.canonical_form(bare)
            return IdentityResult(protomol.to_json(canonical), atom_map=atom_map)

        # A graph-kind algorithm that sorts first by name, but ranks after the kind
        IdentityAlgorithmRegistry.register(
            name="a_graph@0",
            kind=IdentityKind.GRAPH,
            identity_fn=protomol_graph.identity_fn,
            orders={0},
            stores_graph=True,
        )
        IdentityAlgorithmRegistry.register(
            name="z_bondless@1",
            kind=IdentityKind.STEREOISOMER,
            identity_fn=_bondless_fn,
            stores_graph=True,
        )
        with Database(db_path) as db, db.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()
            assert list(stp.stored_graphs()) == ["z_bondless@1", "a_graph@0"]
            assert stp.graph == protomol.StereoMolGraph(
                symbols=["O", "H", "H"], bonds=[]
            )

    def test_graph_survives_new_session(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
    ) -> None:
        """The graph is read back from the `stores_graph` link in a new session."""
        gra = protomol.examples.species()
        geo = protomol.embed(gra).relabel_atoms([2, 0, 1, *range(3, len(gra.symbols))])
        gra = protomol.relabel(gra, [2, 0, 1, *range(3, len(gra.symbols))])
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=GeometryRow(**geo.model_dump()),
                calculation=make_calculation(),
                graph=gra,
            )
            session.add(stp)
            session.commit()
            assert stp.pending_graph is None
            stp_id = stp.id
        with graph_database.session() as session:
            stp = session.get(StationaryPointRow, stp_id)
            assert stp is not None
            assert stp.pending_graph is None
            assert stp.graph == gra
            assert set(stp.stored_graphs()) == {"min_graph@0"}

    def test_no_stores_graph_link(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A point without a `stores_graph` link has no graph."""
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation(), order=1
            )
            session.add(stp)
            session.commit()
            assert stp.graph is None
            assert stp.stored_graphs() == {}

    def test_ts_keeps_graph_on_same_atoms(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
    ) -> None:
        """A TS keeps its graph for a new geometry with the same atoms, not others."""
        ts_gra = protomol.examples.abstraction_ts()
        geo = protomol.embed(protomol.reactants(ts_gra))
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=GeometryRow(**geo.model_dump()),
                calculation=make_calculation(),
                order=1,
                graph=ts_gra,
            )
            session.add(stp)
            session.commit()
            value = _identity_for_algorithm(stp, "protomol_graph@0").value

            stp.geometry = GeometryRow(
                **autogeom.translate(geo, [1, 0, 0]).model_dump()
            )
            session.commit()
            assert _identity_for_algorithm(stp, "protomol_graph@0").value == value
            assert _identity_for_algorithm(stp, "atom_count_graph").value == str(
                len(ts_gra.symbols)
            )
            assert stp.graph == ts_gra

            # Different symbols (or order): the TS can't keep its graph
            n = len(geo.symbols)
            stp.geometry = GeometryRow(
                **geo.relabel_atoms([n - 1, *range(n - 1)]).model_dump()
            )
            session.commit()
            assert _graph_identity_names(stp) == set()
            assert stp.graph is None

    def test_order_change_keeps_graph(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        count_perceptions: list[Geometry],
    ) -> None:
        """A given graph is kept when only `order` changes, and not re-perceived."""
        gra = protomol.examples.species()
        geo = GeometryRow(**protomol.embed(gra).model_dump())
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=geo, calculation=make_calculation(), graph=gra
            )
            session.add(stp)
            session.commit()
            value = _identity_for_algorithm(stp, "min_graph@0").value

            stp.order = 1
            session.commit()
            # The saddle-point algorithm gets the kept graph
            assert _identity_for_algorithm(stp, "protomol_graph@0").value == value
            assert stp.graph == gra
            assert count_perceptions == []

    def test_new_graph_changes_only_graph_links(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A new graph on a stored point regenerates only its graph identities."""
        with graph_database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()
            before = {link.identity.algorithm_name: link for link in stp.identity_links}
            old_graph_id = before["min_graph@0"].identity_id

            # Water given as two fragments: O-H and H
            new_gra = protomol.StereoMolGraph(symbols=["O", "H", "H"], bonds=[(0, 1)])
            stp.graph = new_gra
            assert stp in session.dirty
            assert stp.graph == new_gra
            session.commit()

            after = {link.identity.algorithm_name: link for link in stp.identity_links}
            assert set(after) == set(before)
            for name in ("rdkit_inchi", "rdkit_inchi_conn", "rdkit_smiles"):
                assert after[name] is before[name]
            assert (
                after["hill_formula"].identity_id == before["hill_formula"].identity_id
            )
            new_value = after["min_graph@0"].identity.value
            assert new_value == protomol.canonical_json(new_gra)
            assert after["min_graph@0"].identity_id != old_graph_id
            # The old identity is kept, as identities are never deleted
            assert session.get(IdentityRow, old_graph_id) is not None
            assert stp.pending_graph is None
            assert stp.graph == new_gra

    def test_failed_flush_keeps_pending_graph(
        self,
        graph_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A flush that fails keeps the pending graph for the next try."""
        gra = protomol.from_geometry(make_geometry_water())
        with graph_database.session() as session:
            # A valid point needs a Hessian, so this flush fails
            stp = StationaryPointRow(
                geometry=make_geometry_water(),
                calculation=make_calculation(),
                graph=gra,
                is_validated=True,
            )
            session.add(stp)
            with pytest.raises(ValueError, match="Hessian"):
                session.flush()
            assert stp.pending_graph is gra


def _reversed_identity_fn(
    geo: Geometry,
    gra: AnyGraph | None = None,  # noqa: ARG001
    other_geos: Mapping[str, Geometry] | None = None,  # noqa: ARG001
) -> IdentityResult:
    """A fake canonical identity: the atom count, with the atoms reversed."""
    natoms = geo.atom_count
    atom_map = list(reversed(range(natoms)))
    return IdentityResult(str(natoms), atom_map=atom_map, cache={"natoms": natoms})


def _bad_map_identity_fn(
    geo: Geometry,  # noqa: ARG001
    gra: AnyGraph | None = None,  # noqa: ARG001
    other_geos: Mapping[str, Geometry] | None = None,  # noqa: ARG001
) -> IdentityResult:
    """A broken identity whose atom map repeats an atom."""
    return IdentityResult("bad", atom_map=[0, 0, 1])


@pytest.fixture
def result_database(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Database]:
    """A database with algorithms returning a good and a bad `IdentityResult`."""
    monkeypatch.setattr(
        IdentityAlgorithmRegistry,
        "algorithms",
        list(IdentityAlgorithmRegistry.algorithms),
    )
    IdentityAlgorithmRegistry.register(
        name="reversed@1", kind=IdentityKind.FORMULA, identity_fn=_reversed_identity_fn
    )
    IdentityAlgorithmRegistry.register(
        name="bad_map@1", kind=IdentityKind.FORMULA, identity_fn=_bad_map_identity_fn
    )
    with Database(db_path) as db:
        yield db


class TestIdentityResult:
    """An `IdentityResult` sets the link's `atom_map` and `algorithm_cache`."""

    def test_atom_map_and_cache(
        self,
        result_database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
    ) -> None:
        """A good result is stored on the link; a bad atom map skips the identity."""
        with result_database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            with pytest.warns(IdentityGenerationWarning, match="not a permutation"):
                session.commit()
            session.expire_all()

            link = _link_for_algorithm(stp, "reversed@1")
            assert link.identity.value == "3"
            assert link.atom_map == [2, 1, 0]
            assert link.algorithm_cache == {"natoms": 3}
            names = {i.algorithm_name for i in _identities(stp)}
            assert "bad_map@1" not in names
            assert link.identity.algorithm_cache is None
            # A plain-string identity has neither
            formula = _link_for_algorithm(stp, "hill_formula")
            assert formula.atom_map is None
            assert formula.algorithm_cache is None

    @pytest.mark.parametrize("atom_map", [[0, 1], [0, 1, 3], [0, 0, 1]])
    def test_bad_atom_map_written_directly_raises(
        self,
        database: Database,
        make_calculation: Callable[[], CalculationRow],
        make_geometry_water: Callable[[], GeometryRow],
        atom_map: list[int],
    ) -> None:
        """An atom map that doesn't permute the point's atoms fails the flush."""
        with database.session() as session:
            stp = StationaryPointRow(
                geometry=make_geometry_water(), calculation=make_calculation()
            )
            session.add(stp)
            session.commit()

            link = _link_for_algorithm(stp, "hill_formula")
            link.atom_map = atom_map
            with pytest.raises(ValueError, match=f"'hill_formula'.*{stp.id}"):
                session.flush()
            session.rollback()

            link.atom_map = [1, 2, 0]
            session.commit()
            session.expire_all()
            assert link.atom_map == [1, 2, 0]


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
            smiles_link = _link_for_algorithm(stp1, "rdkit_smiles")
            stp1.identity_links.remove(smiles_link)
            stp1.identity_links.append(
                IdentityStationaryLink(
                    identity=IdentityRow(algorithm_name="rdkit_smiles", value="[H]O[H]")
                )
            )
            session.commit()

            stp2 = StationaryPointRow(geometry=make_geometry_water(), calculation=calc)
            session.add(stp2)
            session.commit()

            assert _identity_for_algorithm(stp2, "rdkit_smiles").value == "[H]O[H]"


def _failing_hash_fn(
    program: str,  # noqa: ARG001
    method: str,  # noqa: ARG001
    basis: str | None,  # noqa: ARG001
    keywords: Any,  # noqa: ANN401, ARG001
) -> str:
    """Hash function that always raises."""
    msg = "cannot hash"
    raise ValueError(msg)


def _empty_hash_fn(
    program: str,  # noqa: ARG001
    method: str,  # noqa: ARG001
    basis: str | None,  # noqa: ARG001
    keywords: Any,  # noqa: ANN401, ARG001
) -> str:
    """Hash function that returns an empty string."""
    return ""


def _long_hash_fn(
    program: str,  # noqa: ARG001
    method: str,  # noqa: ARG001
    basis: str | None,  # noqa: ARG001
    keywords: Any,  # noqa: ANN401, ARG001
) -> str:
    """Hash function that returns a value at the length limit."""
    return "x" * MAX_MODEL_HASH_LENGTH


def _registered(
    name: str,
    hash_fn: ModelHashProtocol,
    programs: set[str] | None = None,
) -> Generator[ModelHashAlgorithm]:
    """Register a test algorithm, and remove it from the registry afterwards."""
    algorithm = ModelHashAlgorithmRegistry.register(
        name, ModelHashKind.FINE, hash_fn, programs=programs
    )
    yield algorithm
    ModelHashAlgorithmRegistry.algorithms.remove(algorithm)


@pytest.fixture
def failing_hash_database(db_path: Path) -> Generator[Database]:
    """A database opened with an always-failing model hash algorithm registered."""
    # Registered before the database opens, so that the algorithm is seeded
    for _ in _registered("failing_test@1", _failing_hash_fn):
        with Database(db_path) as db:
            yield db


def _orca_hash_fn(
    program: str,
    method: str,
    basis: str | None,  # noqa: ARG001
    keywords: Any,  # noqa: ANN401, ARG001
) -> str:
    """Hash function for ORCA models."""
    return f"{program}:{method}"


@pytest.fixture
def orca_database(db_path: Path) -> Generator[Database]:
    """A database opened with an ORCA-only model hash algorithm registered."""
    for _ in _registered("orca_test@1", _orca_hash_fn, programs={"orca"}):
        with Database(db_path) as db:
            yield db


@pytest.fixture
def empty_hash_database(db_path: Path) -> Generator[Database]:
    """A database opened with an empty-valued model hash algorithm registered."""
    for _ in _registered("empty_test@1", _empty_hash_fn):
        with Database(db_path) as db:
            yield db


@pytest.fixture
def long_hash_database(db_path: Path) -> Generator[Database]:
    """A database opened with a too-long-valued model hash algorithm registered."""
    for _ in _registered("long_test@1", _long_hash_fn):
        with Database(db_path) as db:
            yield db


def _hash_values(model: ModelRow) -> dict[str | None, str]:
    """Return the model's hash values keyed by algorithm name."""
    return {link.hash.algorithm_name: link.hash.value for link in model.hash_links}


def _hash_rows(session: Session, algorithm_name: str) -> list[ModelHashRow]:
    """Return every stored hash row of an algorithm."""
    return list(
        session.exec(
            select(ModelHashRow).where(ModelHashRow.algorithm_name == algorithm_name)
        )
    )


class TestModelHashes:
    """Models get hashes from the registered algorithms on flush."""

    def test_new_model_gets_builtin_hashes(self, database: Database) -> None:
        """A new model is linked to one hash per built-in algorithm."""
        with database.session() as session:
            model = ModelRow(program="ORCA", method="B3LYP", basis="6-31G*")
            session.add(model)
            session.commit()

            assert len(model.hash_links) == N_BUILTIN_HASHES
            hashes = _hash_values(model)
            assert set(hashes) == {"minimal@1", "exact@1"}
            assert hashes["minimal@1"] == "b3lyp/6-31g*"
            assert len(hashes["exact@1"]) == 64

    def test_same_method_different_keywords(self, database: Database) -> None:
        """Models differing in keywords share minimal@1 but not exact@1."""
        with database.session() as session:
            models = [
                ModelRow(program="orca", method="b3lyp", keywords={"a": 1}),
                ModelRow(program="orca", method="b3lyp", keywords={"a": 2}),
            ]
            session.add_all(models)
            session.commit()

            assert len(_hash_rows(session, "minimal@1")) == 1
            assert len(_hash_rows(session, "exact@1")) == NDIM_2  # one per model
            assert (
                _hash_values(models[0])["minimal@1"]
                == _hash_values(models[1])["minimal@1"]
            )

    def test_identical_models_share_hash_rows(self, database: Database) -> None:
        """Identical models are stored twice and share their hash rows."""
        with database.session() as session:
            first = ModelRow(program="orca", method="b3lyp", keywords={"a": 1})
            second = ModelRow(program="orca", method="b3lyp", keywords={"a": 1})
            # Same flush: the per-flush cache's job
            session.add_all([first, second])
            session.commit()
            third = ModelRow(program="orca", method="b3lyp", keywords={"a": 1})
            # Later flush: found in the database
            session.add(third)
            session.commit()

            assert len(session.exec(select(ModelRow)).all()) == NDIM_3
            assert len(_hash_rows(session, "minimal@1")) == 1
            assert len(_hash_rows(session, "exact@1")) == 1
            ids = {
                frozenset(link.hash_id for link in m.hash_links)
                for m in (first, second, third)
            }
            assert len(ids) == 1

    def test_failing_hash_warns(self, failing_hash_database: Database) -> None:
        """A hash function that raises is skipped with a warning; the rest attach."""
        with failing_hash_database.session() as session:
            model = ModelRow(program="orca", method="b3lyp")
            session.add(model)
            with pytest.warns(
                ModelHashGenerationWarning, match=r"failing_test@1.*ValueError"
            ):
                session.flush()

            assert set(_hash_values(model)) == {"minimal@1", "exact@1"}

    def test_empty_hash_skipped(self, empty_hash_database: Database) -> None:
        """An empty hash value is skipped with a warning."""
        with empty_hash_database.session() as session:
            model = ModelRow(program="orca", method="b3lyp")
            session.add(model)
            with pytest.warns(ModelHashGenerationWarning, match="empty hash"):
                session.flush()

            assert "empty_test@1" not in _hash_values(model)

    def test_long_hash_skipped(self, long_hash_database: Database) -> None:
        """A hash value at the length limit is skipped with a warning."""
        with long_hash_database.session() as session:
            model = ModelRow(program="orca", method="b3lyp")
            session.add(model)
            with pytest.warns(ModelHashGenerationWarning, match="255 characters"):
                session.flush()

            assert set(_hash_values(model)) == {"minimal@1", "exact@1"}

    def test_edit_keywords_rehashes(self, database: Database) -> None:
        """Reassigning or extending keywords replaces exact@1 and keeps minimal@1."""
        with database.session() as session:
            model = ModelRow(program="orca", method="b3lyp", keywords={"a": 1})
            session.add(model)
            session.commit()
            links = {
                link.hash.algorithm_name: link.hash_id for link in model.hash_links
            }
            old_exact = _hash_values(model)["exact@1"]

            model.keywords = {"a": 2}  # reassigned
            session.commit()
            reassigned = _hash_values(model)["exact@1"]
            assert reassigned != old_exact

            model.keywords["b"] = 3  # top-level key added in place
            session.commit()
            added = _hash_values(model)["exact@1"]
            assert added not in {old_exact, reassigned}

            new_links = {
                link.hash.algorithm_name: link.hash_id for link in model.hash_links
            }
            assert len(model.hash_links) == N_BUILTIN_HASHES
            assert new_links["minimal@1"] == links["minimal@1"]
            assert new_links["exact@1"] != links["exact@1"]
            # The old exact@1 row stays in the table
            assert len(_hash_rows(session, "exact@1")) == NDIM_3

    def test_edit_method_rehashes(self, database: Database) -> None:
        """Changing the method replaces the minimal@1 link."""
        with database.session() as session:
            model = ModelRow(program="orca", method="b3lyp", basis="def2-svp")
            session.add(model)
            session.commit()

            model.method = "pbe0"
            session.commit()

            assert _hash_values(model)["minimal@1"] == "pbe0/def2-svp"

    def test_unrelated_edit_keeps_links(self, database: Database) -> None:
        """Editing `program_version` doesn't touch the hash links."""
        with database.session() as session:
            model = ModelRow(program="orca", method="b3lyp")
            session.add(model)
            session.commit()
            before = {link.hash_id for link in model.hash_links}

            model.program_version = "6.1"
            session.commit()

            assert {link.hash_id for link in model.hash_links} == before

    def test_program_restricted_algorithm(self, orca_database: Database) -> None:
        """A program-restricted algorithm links models of that program only."""
        with orca_database.session() as session:
            orca = ModelRow(program="ORCA", method="b3lyp")
            psi4 = ModelRow(program="psi4", method="b3lyp")
            session.add_all([orca, psi4])
            session.commit()

            assert _hash_values(orca)["orca_test@1"] == "ORCA:b3lyp"
            assert "orca_test@1" not in _hash_values(psi4)

    def test_delete_model_keeps_hash_rows(self, database: Database) -> None:
        """Deleting a model removes its links and leaves the hash rows."""
        with database.session() as session:
            model = ModelRow(program="orca", method="b3lyp")
            session.add(model)
            session.commit()

            session.delete(model)
            session.commit()

            assert session.exec(select(ModelHashLink)).all() == []
            assert len(session.exec(select(ModelHashRow)).all()) == N_BUILTIN_HASHES
