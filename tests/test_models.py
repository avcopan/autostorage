"""Models module tests."""

import json
import tempfile
import uuid
import zlib
from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest
from autogeom import ureg
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select, text

from autostorage import (
    energy_property_kind,
    gradient_property_kind,
    hessian_property_kind,
)
from autostorage.database import Database
from autostorage.models import (
    CalculationGeometryLink,
    CalculationRow,
    CalculationTrajectoryLink,
    GeometryRow,
    GeometryTrajectoryLink,
    IdentityAlgorithmRow,
    IdentityRow,
    IdentityStationaryLink,
    ModelRow,
    PropertyValueRow,
    StageRow,
    StageStationaryLink,
    StationaryPointRow,
    StepRow,
    StepValidationLink,
    TrajectoryAxisRow,
    TrajectoryRow,
    ValidationRow,
)
from autostorage.types import AxisKind, Role


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
def hydrogen() -> GeometryRow:
    """Hydrogen GeometryRow fixture."""
    return GeometryRow(symbols=["H", "H"], coordinates=[[0.32, 0, 0], [-0.32, 0, 0]])


@pytest.fixture
def water() -> GeometryRow:
    """Water GeometryRow fixture."""
    return GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=[[0.0, 0.0, 0.0], [0.0, 0.76, 0.59], [0.0, -0.76, 0.59]],
    )


@pytest.fixture
def b3lyp() -> ModelRow:
    """B3LYP ModelRow fixture."""
    return ModelRow(program="test", method="b3lyp")


@pytest.fixture
def calculation(b3lyp: ModelRow) -> CalculationRow:
    """Test CalculationRow fixture."""
    return CalculationRow(
        model=b3lyp,
        calc_type="test",
        input_provenance={"source": "test"},
        output_provenance={"status": "success"},
    )


class TestGeometryRow:
    """Tests for GeometryRow model."""

    def test_geometry_default_charge_and_spin(
        self, database: Database, hydrogen: GeometryRow
    ) -> None:
        """GeometryRow stores charge=0, spin=0 as default values."""
        with database.session() as session:
            session.add(hydrogen)
            session.commit()

            assert hydrogen.charge == 0
            assert hydrogen.spin == 0

    def test_create_geometry_with_list_coordinates(self, database: Database) -> None:
        """GeometryRow can be created with list coordinates."""
        with database.session() as session:
            geo = GeometryRow(
                symbols=["C", "H"],
                coordinates=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                spin=1,
            )
            session.add(geo)
            session.commit()

            assert geo.id is not None
            assert isinstance(geo.coordinates, np.ndarray)
            assert geo.coordinates.shape == (2, 3)

    def test_create_geometry_with_numpy_coordinates(self, database: Database) -> None:
        """GeometryRow can be created with numpy array coordinates."""
        with database.session() as session:
            coords = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
            geom = GeometryRow(symbols=["C", "H"], coordinates=coords, spin=1)
            session.add(geom)
            session.commit()

            assert geom.id is not None
            assert isinstance(geom.coordinates, np.ndarray)
            np.testing.assert_array_equal(geom.coordinates, coords)

    def test_geometry_charge_and_spin(self, database: Database) -> None:
        """GeometryRow stores charge and spin correctly."""
        with database.session() as session:
            geo = GeometryRow(
                symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], charge=1, spin=1
            )
            session.add(geo)
            session.commit()

            assert geo.charge == 1
            assert geo.spin == 1

    def test_geometry_symbols_canonicalized(self) -> None:
        """Atomic symbols are validated and canonicalized by autogeom."""
        geo = GeometryRow(
            symbols=["o", "h", "h"],
            coordinates=[[0.0, 0.0, 0.0], [0.0, 0.76, 0.59], [0.0, -0.76, 0.59]],
        )
        assert geo.symbols == ["O", "H", "H"]

    @pytest.mark.parametrize(
        ("symbols", "spin"), [(["Xx"], 0), (["C", "H"], 0), (["C", "H"], -1)]
    )
    def test_invalid_geometry_raises(self, symbols: list[str], spin: int) -> None:
        """Unknown elements and inconsistent spins are rejected."""
        with pytest.raises(ValidationError):
            GeometryRow(
                symbols=symbols, coordinates=np.zeros((len(symbols), 3)), spin=spin
            )

    @pytest.mark.parametrize(
        ("coordinates", "z"),
        [
            ([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]], 1.0),
            (
                ureg.Quantity(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]]), "bohr"),
                0.529177,
            ),
            (ureg.Quantity(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.1]]), "nm"), 1.0),
        ],
    )
    def test_coordinates_stored_in_angstrom(
        self, database: Database, coordinates: object, z: float
    ) -> None:
        """`pint` coordinates are converted to Angstrom; plain ones are kept as is."""
        geo = GeometryRow(symbols=["H", "H"], coordinates=coordinates)
        assert geo.coordinates[1, 2] == pytest.approx(z, rel=1e-5)
        with database.session() as session:
            session.add(geo)
            session.commit()
            session.expire_all()
            assert geo.coordinates[1, 2] == pytest.approx(z, rel=1e-5)

    def test_pint_coordinates_converted_on_assignment(self) -> None:
        """Coordinates assigned as a `pint` quantity are converted to Angstrom."""
        geo = GeometryRow(symbols=["H", "H"], coordinates=np.zeros((2, 3)))
        bohr = ureg.Quantity(np.array([[0, 0, 0], [0, 0, 1.0]]), "bohr")
        # The validator accepts quantities, though the field is typed as the result
        geo.coordinates = bohr  # ty: ignore[invalid-assignment]
        assert geo.coordinates[1, 2] == pytest.approx(0.529177, rel=1e-5)

    def test_pint_coordinates_incompatible_units(self) -> None:
        """Coordinates without length units are rejected."""
        with pytest.raises(ValidationError, match="length units"):
            GeometryRow(
                symbols=["H", "H"],
                coordinates=ureg.Quantity(np.zeros((2, 3)), "hartree"),
            )

    def test_relabel_atoms_creates_new_row(
        self, database: Database, water: GeometryRow
    ) -> None:
        """`relabel_atoms` returns a new row that can be persisted."""
        with database.session() as session:
            session.add(water)
            session.commit()

            relabeled = water.relabel_atoms([1, 0, 2])
            session.add(relabeled)
            session.commit()

            assert relabeled.id != water.id
            assert session.get(GeometryRow, relabeled.id) is not None
            assert relabeled.symbols == ["H", "O", "H"]
            assert len(session.exec(select(GeometryRow)).all()) == 2

    def test_geometry_relationships(
        self, database: Database, hydrogen: GeometryRow
    ) -> None:
        """GeometryRow relationships are initially empty."""
        with database.session() as session:
            session.add(hydrogen)
            session.commit()

            assert hydrogen.properties == []
            assert hydrogen.stationary_points == []
            assert hydrogen.trajectory_links == []
            assert hydrogen.calculation_links == []


class TestTrajectoryRow:
    """Tests for TrajectoryRow model."""

    def test_create_trajectory_with_ndim(self, database: Database) -> None:
        """TrajectoryRow can be created with ndim specified."""
        with database.session() as session:
            traj = TrajectoryRow(ndim=3)
            session.add(traj)
            session.commit()

            assert traj.id is not None
            assert traj.ndim == 3

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

    @staticmethod
    def _grid_trajectory(shape: tuple[int, int]) -> TrajectoryRow:
        """Build a 2D trajectory of H2 geometries, with bond length 1 + i + j/10."""
        traj = TrajectoryRow()
        # Add links in reverse so that ordering by index is actually exercised
        for i in reversed(range(shape[0])):
            for j in reversed(range(shape[1])):
                geo = GeometryRow(
                    symbols=["H", "H"],
                    coordinates=[[0.0, 0.0, 0.0], [0.0, 0.0, 1 + i + j / 10]],
                )
                traj.geometry_links.append(
                    GeometryTrajectoryLink(geometry=geo, index=[i, j])
                )
        return traj

    @staticmethod
    def _bond_lengths(geos: list[GeometryRow]) -> list[float]:
        return [float(geo.coordinates[1, 2]) for geo in geos]

    def test_geometries_along(self, database: Database) -> None:
        """`geometries_along` slices one dimension in index order."""
        with database.session() as session:
            traj = self._grid_trajectory((3, 2))
            session.add(traj)
            session.commit()

            assert self._bond_lengths(traj.geometries_along()) == pytest.approx(
                [1.0, 2.0, 3.0]
            )
            assert self._bond_lengths(traj.geometries_along(0, [1])) == pytest.approx(
                [1.1, 2.1, 3.1]
            )
            assert self._bond_lengths(traj.geometries_along(1, [2])) == pytest.approx(
                [3.0, 3.1]
            )
            assert traj.geometries_along(0, [5]) == []

    def test_geometries_along_infers_ndim(self) -> None:
        """`geometries_along` works before `ndim` is inferred on flush."""
        traj = self._grid_trajectory((2, 2))
        assert traj.ndim is None
        assert self._bond_lengths(traj.geometries_along(1)) == pytest.approx([1.0, 1.1])

    @pytest.mark.parametrize(
        ("axis", "at"), [(2, None), (-1, None), (0, [0, 0]), (0, [])]
    )
    def test_geometries_along_invalid(self, axis: int, at: list[int] | None) -> None:
        """Out-of-range axes and mis-sized `at` indices are rejected."""
        traj = self._grid_trajectory((2, 2))
        with pytest.raises(ValueError, match=r"out of range|Expected"):
            traj.geometries_along(axis, at)

    def test_geometries_along_empty(self) -> None:
        """A trajectory without indexed geometries cannot be sliced."""
        with pytest.raises(ValueError, match="no indexed geometries"):
            TrajectoryRow(ndim=1).geometries_along()

    def test_view(self) -> None:
        """`view` animates the geometries along one dimension."""
        traj = self._grid_trajectory((3, 2))
        view = traj.view(axis=0, at=[1], interval=100)
        script = view.startjs + view.endjs
        assert "addModelsAsFrames" in script
        assert '"interval": 100' in script
        assert script.count("Geometry(q=0, s=0)") == 3
        assert "1.10000000" in script
        assert "3.10000000" in script
        assert "1.00000000" not in script

    def test_view_empty_slice(self) -> None:
        """`view` rejects a slice with no geometries."""
        traj = self._grid_trajectory((2, 2))
        with pytest.raises(ValueError, match="No geometries"):
            traj.view(axis=0, at=[5])


def _hooh(phi: float) -> GeometryRow:
    """HOOH with an H-O-O-H dihedral of `phi` degrees."""
    th = np.radians(phi)
    return GeometryRow(
        symbols=["H", "O", "O", "H"],
        coordinates=[[0, 0, 1], [0, 0, 0], [0, 1, 0], [np.sin(th), 1, np.cos(th)]],
    )


class TestTrajectoryAxisRow:
    """Tests for TrajectoryAxisRow and the values of a trajectory's geometries."""

    PHIS = (0.0, 60.0, 120.0, 180.0)

    @classmethod
    def _scan(cls, **axis_kwargs: object) -> TrajectoryRow:
        """Build a dihedral scan of HOOH, with an axis describing dimension 0."""
        traj = TrajectoryRow()
        traj.axes.append(
            TrajectoryAxisRow(
                axis=0,
                kind=AxisKind.DIHEDRAL,
                keys=[0, 1, 2, 3],
                **axis_kwargs,  # ty: ignore[invalid-argument-type]
            )
        )
        for i, phi in reversed(list(enumerate(cls.PHIS))):
            traj.geometry_links.append(
                GeometryTrajectoryLink(geometry=_hooh(phi), index=[i])
            )
        return traj

    def test_values_measured_on_flush(self, database: Database) -> None:
        """Missing dihedral values are measured, in degrees by default."""
        with database.session() as session:
            traj = self._scan(label="H-O-O-H torsion")
            session.add(traj)
            session.commit()
            session.expire_all()

            assert traj.axes[0].units == "degree"
            assert traj.axes[0].label == "H-O-O-H torsion"
            assert traj.values_along() == pytest.approx(self.PHIS)
            assert traj.values_along(units="radian") == pytest.approx(
                np.radians(self.PHIS)
            )

    def test_values_in_axis_units(self, database: Database) -> None:
        """Measured values are stored in the axis's units."""
        with database.session() as session:
            traj = self._scan(units="radian")
            session.add(traj)
            session.commit()
            assert traj.values_along() == pytest.approx(np.radians(self.PHIS))

    @pytest.mark.parametrize(
        ("kind", "keys", "expected"),
        [("distance", [1, 2], 1.0), ("angle", [0, 1, 2], 90.0)],
    )
    def test_measure(self, kind: str, keys: list[int], expected: float) -> None:
        """Distances are measured in Angstrom and angles in degrees."""
        axis = TrajectoryAxisRow(axis=0, kind=AxisKind(kind), keys=keys)
        assert axis.measure(_hooh(90.0)) == pytest.approx(expected)

    def test_other_axis_is_not_measured(self, database: Database) -> None:
        """`OTHER` axes keep given values, converted, and leave missing ones None."""
        with database.session() as session:
            traj = TrajectoryRow()
            traj.axes.append(
                TrajectoryAxisRow(axis=0, kind=AxisKind.OTHER, units="bohr")
            )
            given = GeometryTrajectoryLink(
                geometry=_hooh(0.0),
                index=[0],
                values=[ureg.Quantity(0.0529177, "nm")],  # ty: ignore[invalid-argument-type]
            )
            missing = GeometryTrajectoryLink(geometry=_hooh(60.0), index=[1])
            traj.geometry_links.extend([given, missing])
            session.add(traj)
            session.commit()

            assert given.values == pytest.approx([1.0], rel=1e-5)
            assert missing.values == [None]
            np.testing.assert_allclose(traj.values_along(), [1.0, np.nan], rtol=1e-5)

    def test_given_values_kept_and_converted(self, database: Database) -> None:
        """Given values are kept, and quantities converted to the axis's units."""
        with database.session() as session:
            traj = self._scan()
            links = sorted(traj.geometry_links, key=lambda link: link.index or [])
            links[0].values = [1.5]
            links[1].values = [ureg.Quantity(np.pi / 2, "radian")]  # ty: ignore[invalid-assignment]
            session.add(traj)
            session.commit()

            assert traj.values_along() == pytest.approx([1.5, 90.0, 120.0, 180.0])

    def test_axis_added_later_fills_values(self, database: Database) -> None:
        """Adding an axis to a stored trajectory fills its geometries' values."""
        with database.session() as session:
            traj = self._scan()
            traj.axes.clear()
            session.add(traj)
            session.commit()
            assert all(link.values is None for link in traj.geometry_links)

            session.add(
                TrajectoryAxisRow(
                    trajectory_id=traj.id, axis=0, kind="dihedral", keys=[0, 1, 2, 3]
                )
            )
            session.commit()
            session.expire_all()
            assert traj.values_along() == pytest.approx(self.PHIS)

    def test_values_without_axes(self, database: Database) -> None:
        """Plain values are accepted on dimensions without an axis."""
        with database.session() as session:
            traj = TrajectoryRow()
            link = GeometryTrajectoryLink(geometry=_hooh(0), index=[0], values=[2])
            traj.geometry_links.append(link)
            session.add(traj)
            session.commit()
            assert link.values == [2.0]
            with pytest.raises(ValueError, match="no TrajectoryAxisRow"):
                traj.values_along(units="degree")

    @pytest.mark.parametrize(
        ("axis_kwargs", "values", "match"),
        [
            ({"keys": [0, 1, 2]}, None, "needs 4 atom keys"),
            ({"units": "furlongs_per_banana"}, None, "Invalid units"),
            ({"units": "angstrom"}, None, "not valid for a dihedral"),
            ({"axis": 1}, None, "out of range"),
            ({"kind": "torsion"}, None, "Unknown axis kind"),
            ({}, [1.0, 2.0], "does not match trajectory ndim"),
            ({}, [ureg.Quantity(1.0, "hartree")], "Expected units compatible"),
        ],
    )
    def test_invalid(
        self,
        database: Database,
        axis_kwargs: dict[str, object],
        values: list[object] | None,
        match: str,
    ) -> None:
        """Invalid axes and values are rejected on flush."""
        traj = TrajectoryRow()
        traj.axes.append(
            TrajectoryAxisRow(
                **{"axis": 0, "kind": "dihedral", "keys": [0, 1, 2, 3], **axis_kwargs}  # ty: ignore[invalid-argument-type]
            )
        )
        traj.geometry_links.append(
            GeometryTrajectoryLink(geometry=_hooh(0), index=[0], values=values)  # ty: ignore[invalid-argument-type]
        )
        with database.session() as session:
            session.add(traj)
            with pytest.raises(ValueError, match=match):
                session.commit()

    @pytest.mark.parametrize(
        ("values", "match"),
        [
            ([ureg.Quantity(1.0, "degree")], "has no TrajectoryAxisRow"),
            ([1.0], "require an index"),
        ],
    )
    def test_invalid_values_without_axis(
        self, database: Database, values: list[object], match: str
    ) -> None:
        """Quantities need an axis, and values need an index."""
        traj = TrajectoryRow()
        index = None if match == "require an index" else [0]
        traj.geometry_links.append(
            GeometryTrajectoryLink(geometry=_hooh(0), index=index, values=values)  # ty: ignore[invalid-argument-type]
        )
        with database.session() as session:
            session.add(traj)
            with pytest.raises(ValueError, match=match):
                session.commit()

    def test_values_along_incompatible_units(self) -> None:
        """`values_along` rejects units incompatible with the axis."""
        traj = self._scan(units="degree")
        with pytest.raises(ValueError, match="Cannot convert"):
            traj.values_along(units="bohr")

    def test_axes_deleted_with_trajectory(self, database: Database) -> None:
        """Deleting a trajectory deletes its axes."""
        with database.session() as session:
            traj = self._scan()
            session.add(traj)
            session.commit()
            session.delete(traj)
            session.commit()
            assert session.exec(select(TrajectoryAxisRow)).all() == []


class TestModelRow:
    """Tests for ModelRow model."""

    def test_create_model_minimal(self, database: Database, b3lyp: ModelRow) -> None:
        """ModelRow can be created with minimal required fields."""
        with database.session() as session:
            session.add(b3lyp)
            session.commit()

            assert b3lyp.id is not None
            assert b3lyp.program == "test"
            assert b3lyp.method == "b3lyp"
            assert b3lyp.basis is None
            assert b3lyp.program_version is None
            assert b3lyp.keywords == {}

    def test_create_model_complete(self, database: Database) -> None:
        """ModelRow can be created with all fields specified."""
        with database.session() as session:
            model = ModelRow(
                program="orca",
                program_version="6.1.1",
                method="MP2",
                basis="cc-pvdz",
                keywords={"convergence": "tight", "scf_type": "df"},
            )
            session.add(model)
            session.commit()

            assert model.id is not None
            assert model.program_version == "6.1.1"
            assert model.basis == "cc-pvdz"
            assert model.keywords == {"convergence": "tight", "scf_type": "df"}

    def test_keywords_in_place_change_persists(
        self, database: Database, b3lyp: ModelRow
    ) -> None:
        """In-place edits of `keywords` are persisted."""
        with database.session() as session:
            session.add(b3lyp)
            session.commit()
            assert b3lyp.keywords is not None
            b3lyp.keywords["scf_type"] = "df"
            session.commit()

        with database.session() as session:
            model = session.exec(select(ModelRow)).one()
            assert model.keywords == {"scf_type": "df"}


class TestCalculationRow:
    """Tests for CalculationRow model."""

    def test_create_calculation(
        self, database: Database, b3lyp: ModelRow, calculation: CalculationRow
    ) -> None:
        """CalculationRow can be created with a model reference."""
        with database.session() as session:
            session.add_all([b3lyp, calculation])
            session.commit()

            assert calculation.id is not None
            assert calculation.model_id == b3lyp.id
            assert calculation.calc_type == "test"
            assert calculation.input_provenance == {"source": "test"}
            assert calculation.output_provenance == {"status": "success"}

    def test_calculation_relationships(
        self, database: Database, b3lyp: ModelRow, calculation: CalculationRow
    ) -> None:
        """CalculationRow relationships are initially empty."""
        with database.session() as session:
            session.add_all([b3lyp, calculation])
            session.commit()

            assert calculation.properties == []
            assert calculation.validations == []
            assert calculation.stationary_points == []
            assert calculation.geometry_links == []
            assert calculation.trajectory_links == []

    def test_calculation_model_relationship(
        self, database: Database, b3lyp: ModelRow, calculation: CalculationRow
    ) -> None:
        """CalculationRow.model relationship works correctly."""
        with database.session() as session:
            session.add_all([b3lyp, calculation])
            session.commit()

            assert calculation.model is not None
            assert calculation.model_id == b3lyp.id

    def test_calculation_requires_model(self, database: Database) -> None:
        """CalculationRow requires a valid model_id."""
        with database.session() as session:
            calc = CalculationRow(model_id=uuid.uuid4(), calc_type="energy")
            session.add(calc)

            with pytest.raises(IntegrityError):
                session.commit()

    def test_provenance_in_place_change_persists(
        self, database: Database, calculation: CalculationRow
    ) -> None:
        """In-place edits of the provenance dicts are persisted."""
        with database.session() as session:
            session.add(calculation)
            session.commit()
            assert calculation.input_provenance is not None
            assert calculation.output_provenance is not None
            calculation.input_provenance["step"] = 2
            del calculation.output_provenance["status"]
            session.commit()

        with database.session() as session:
            calc = session.exec(select(CalculationRow)).one()
            assert calc.input_provenance == {"source": "test", "step": 2}
            assert calc.output_provenance == {}


class TestResultRows:
    """Tests for property value rows (energy, gradient, Hessian)."""

    def test_create_energy_property_row(
        self,
        database: Database,
        b3lyp: ModelRow,
        calculation: CalculationRow,
        hydrogen: GeometryRow,
    ) -> None:
        """`PropertyValueRow` can be created with `energy_property_kind`."""
        with database.session() as session:
            ene = PropertyValueRow(
                geometry=hydrogen,
                calculation=calculation,
                property_kind_name=energy_property_kind.name,
                value=0.0,
            )
            session.add_all([b3lyp, calculation, hydrogen, ene])
            session.commit()

            assert ene.id is not None
            assert ene.value.dtype == np.float64
            assert ene.value == 0.0
            assert ene.geometry_id == hydrogen.id
            assert ene.calculation_id == calculation.id
            assert ene.property_kind_name == energy_property_kind.name

    def test_create_gradient_property_row(
        self,
        database: Database,
        b3lyp: ModelRow,
        calculation: CalculationRow,
        hydrogen: GeometryRow,
    ) -> None:
        """`PropertyValueRow` can be created with `gradient_property_kind`."""
        with database.session() as session:
            shape = 3 * hydrogen.atom_count
            grad = PropertyValueRow(
                geometry=hydrogen,
                calculation=calculation,
                property_kind_name=gradient_property_kind.name,
                value=np.zeros(shape),
            )
            session.add_all([b3lyp, calculation, hydrogen, grad])
            session.commit()

            assert grad.id is not None
            np.testing.assert_array_equal(grad.value, np.zeros(shape))
            assert grad.geometry_id == hydrogen.id
            assert grad.calculation_id == calculation.id
            assert grad.property_kind_name == gradient_property_kind.name

    def test_create_hessian_property_row(
        self,
        database: Database,
        b3lyp: ModelRow,
        calculation: CalculationRow,
        hydrogen: GeometryRow,
    ) -> None:
        """`PropertyValueRow` can be created with `hessian_property_kind`."""
        with database.session() as session:
            shape = (3 * hydrogen.atom_count, 3 * hydrogen.atom_count)
            hess = PropertyValueRow(
                geometry=hydrogen,
                calculation=calculation,
                property_kind_name=hessian_property_kind.name,
                value=np.zeros(shape),
            )
            session.add_all([b3lyp, calculation, hydrogen, hess])
            session.commit()

            assert hess.id is not None
            np.testing.assert_array_equal(hess.value, np.zeros(shape))
            assert hess.value.dtype == np.float32
            assert hess.geometry_id == hydrogen.id
            assert hess.calculation_id == calculation.id
            assert hess.property_kind_name == hessian_property_kind.name


class TestValidationRow:
    """Tests for ValidationRow model."""

    def test_create_validation(
        self, database: Database, b3lyp: ModelRow, calculation: CalculationRow
    ) -> None:
        """ValidationRow can be created with calculation reference."""
        with database.session() as session:
            validation = ValidationRow(
                calculation=calculation, method="irc", extras={"convergence": "tight"}
            )
            session.add_all([b3lyp, calculation, validation])
            session.commit()

            assert validation.id is not None
            assert validation.method == "irc"
            assert validation.extras == {"convergence": "tight"}

    def test_validation_extras_default(
        self, database: Database, b3lyp: ModelRow, calculation: CalculationRow
    ) -> None:
        """ValidationRow extras default to empty dict."""
        with database.session() as session:
            validation = ValidationRow(calculation=calculation, method="irc")
            session.add_all([b3lyp, calculation, validation])
            session.commit()

            assert validation.extras == {}


class TestStationaryPointRow:
    """Tests for StationaryPointRow model."""

    def test_create_stationary_point(
        self,
        database: Database,
        b3lyp: ModelRow,
        calculation: CalculationRow,
        water: GeometryRow,
    ) -> None:
        """StationaryPointRow can be created with default values."""
        with database.session() as session:
            stp = StationaryPointRow(geometry=water, calculation=calculation)
            session.add_all([b3lyp, calculation, water, stp])
            session.commit()

            assert stp.id is not None
            assert stp.order == 0
            assert stp.is_pseudo is False
            assert stp.is_validated is False

            assert stp.geometry_id == water.id
            assert stp.calculation_id == calculation.id

            assert len(stp.identity_links) >= 1  # Auto-populated

    def test_create_transition_state(
        self,
        database: Database,
        b3lyp: ModelRow,
        calculation: CalculationRow,
        water: GeometryRow,
    ) -> None:
        """StationaryPointRow can represent a transition state (order=1)."""
        with database.session() as session:
            stp = StationaryPointRow(geometry=water, calculation=calculation, order=1)
            session.add_all([b3lyp, calculation, water, stp])
            session.commit()

            assert stp.order == 1


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
            stage1, stage2 = sorted(
                [StageRow(is_ts=False), StageRow(is_ts=False)], key=lambda s: str(s.id)
            )
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
            stage1, stage2 = sorted(
                [StageRow(is_ts=False), StageRow(is_ts=False)], key=lambda s: str(s.id)
            )
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
        """IdentityRow can be created with an algorithm and value."""
        with database.session() as session:
            algorithm = session.exec(
                select(IdentityAlgorithmRow).where(
                    col(IdentityAlgorithmRow.name) == "rdkit_inchi"
                )
            ).one()
            identity = IdentityRow(
                algorithm_name=algorithm.name,
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity)
            session.commit()

            assert identity.id is not None
            assert identity.algorithm.kind == "stereoisomer"
            assert identity.algorithm.name == "rdkit_inchi"
            assert identity.value == "InChI=1S/CH4/h1H4"

    def test_identity_unique_constraint(self, database: Database) -> None:
        """IdentityRow enforces unique constraint on algorithm and value."""
        with database.session() as session:
            algorithm = session.exec(
                select(IdentityAlgorithmRow).where(
                    col(IdentityAlgorithmRow.name) == "rdkit_inchi"
                )
            ).one()
            identity1 = IdentityRow(
                algorithm_name=algorithm.name,
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity1)
            session.flush()

            # Try to create duplicate identity
            identity2 = IdentityRow(
                algorithm_name=algorithm.name,
                value="InChI=1S/CH4/h1H4",
            )
            session.add(identity2)

            with pytest.raises(IntegrityError):
                session.commit()

    def test_identity_relationships(self, database: Database) -> None:
        """IdentityRow relationships are initially empty."""
        with database.session() as session:
            algorithm = session.exec(
                select(IdentityAlgorithmRow).where(
                    col(IdentityAlgorithmRow.name) == "rdkit_inchi"
                )
            ).one()
            identity = IdentityRow(
                algorithm_name=algorithm.name, value="InChI=1S/CH4/h1H4"
            )
            session.add(identity)
            session.commit()

            assert identity.stationary_links == []


class TestLinkModels:
    """Tests for link/association table models."""

    @pytest.mark.parametrize("deleted", ["geometry", "calculation", "model"])
    def test_delete_row_deletes_its_data(
        self, database: Database, calculation: CalculationRow, deleted: str
    ) -> None:
        """Deleting a geometry, calculation, or model deletes the data that needs it.

        Properties, stationary points (with their identity and stage links), and
        validations go; geometries, stages, steps, and identities are kept.
        """
        with database.session() as session:
            geo = GeometryRow(symbols=["H", "H"], coordinates=[[0, 0, 0], [0, 0, 0.74]])
            stage1, stage2 = StageRow(), StageRow()
            point = StationaryPointRow(
                geometry=geo, calculation=calculation, stages=[stage1]
            )
            step = StepRow(stage1=stage1, stage2=stage2, is_barrierless=True)
            step.validations.append(
                ValidationRow(calculation=calculation, method="irc")
            )
            energy = PropertyValueRow(
                geometry=geo,
                calculation=calculation,
                property_kind_name=energy_property_kind.name,
                value=-1.0,
            )
            session.add_all([point, step, energy])
            session.commit()
            assert session.exec(select(IdentityStationaryLink)).all()

            rows = {
                "geometry": geo,
                "calculation": calculation,
                "model": calculation.model,
            }
            session.delete(rows[deleted])
            session.commit()

            point_data = [
                PropertyValueRow,
                StationaryPointRow,
                IdentityStationaryLink,
                StageStationaryLink,
            ]
            calculation_data = [*point_data, ValidationRow, StepValidationLink]
            gone, kept = {
                "geometry": (point_data, [CalculationRow, ValidationRow]),
                "calculation": ([*calculation_data, CalculationRow], [GeometryRow]),
                "model": ([*calculation_data, CalculationRow, ModelRow], [GeometryRow]),
            }[deleted]
            for row_cls in gone:
                assert session.exec(select(row_cls)).all() == [], row_cls
            for row_cls in [*kept, StageRow, StepRow, IdentityRow]:
                assert session.exec(select(row_cls)).all(), row_cls

    @pytest.mark.parametrize("deleted", ["geometry", "trajectory", "calculation"])
    def test_delete_row_deletes_its_links(
        self, database: Database, calculation: CalculationRow, deleted: str
    ) -> None:
        """Deleting a row deletes its link rows, but not the rows they link to."""
        with database.session() as session:
            geo = GeometryRow(symbols=["H", "H"], coordinates=[[0, 0, 0], [0, 0, 0.74]])
            traj = TrajectoryRow()
            traj.geometry_links.append(GeometryTrajectoryLink(geometry=geo, index=[0]))
            calculation.geometry_links.append(
                CalculationGeometryLink(geometry=geo, role=Role.INPUT)
            )
            calculation.trajectory_links.append(
                CalculationTrajectoryLink(trajectory=traj, role=Role.OUTPUT)
            )
            rows = {"geometry": geo, "trajectory": traj, "calculation": calculation}
            session.add_all(rows.values())
            session.commit()

            session.delete(rows[deleted])
            session.commit()

            links = {
                "geometry": [GeometryTrajectoryLink, CalculationGeometryLink],
                "trajectory": [GeometryTrajectoryLink, CalculationTrajectoryLink],
                "calculation": [CalculationGeometryLink, CalculationTrajectoryLink],
            }
            for link_cls in links[deleted]:
                assert session.exec(select(link_cls)).all() == []
            for name, row in rows.items():
                if name != deleted:
                    assert session.get(type(row), row.id) is not None

    def test_calculation_geometry_link(self, database: Database) -> None:
        """CalculationGeometryLink can be created with role."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="energy")
            session.add(calc)
            session.flush()

            geom = GeometryRow(symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], spin=2)
            session.add(geom)
            session.flush()

            link = CalculationGeometryLink(
                calculation=calc, geometry=geom, role=Role.INPUT
            )
            session.add(link)
            session.commit()

            assert link.role == Role.INPUT
            assert link.geometry_id == geom.id
            assert link.calculation_id == calc.id

    def test_geometry_trajectory_link(self, database: Database) -> None:
        """GeometryTrajectoryLink can be created with index."""
        with database.session() as session:
            geom = GeometryRow(symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], spin=2)
            traj = TrajectoryRow(ndim=2)
            session.add_all([geom, traj])
            session.flush()

            link = GeometryTrajectoryLink(
                geometry=geom, trajectory_id=traj.id, index=[0, 0]
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
                calculation=calc, trajectory_id=traj.id, role="output"
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

            geom = GeometryRow(symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], spin=2)
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry=geom, calculation=calc)
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

            validation = ValidationRow(calculation=calc, method="irc")
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

            geom = GeometryRow(symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], spin=2)
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry=geom, calculation=calc)
            # Add `stat_pt` before the query below, which triggers an
            # autoflush: flushing a transient object that was only attached
            # via a backref (not yet `session.add`-ed) raises a SAWarning.
            session.add(stat_pt)
            smiles_algorithm = session.exec(
                select(IdentityAlgorithmRow).where(
                    col(IdentityAlgorithmRow.name) == "rdkit_smiles"
                )
            ).one()
            identity = IdentityRow(algorithm_name=smiles_algorithm.name, value="C")
            session.add(identity)
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
            assert link.identity_cache is None

    @pytest.fixture
    def identity_link(
        self, database: Database, calculation: CalculationRow, water: GeometryRow
    ) -> Generator[tuple[Session, IdentityStationaryLink]]:
        """An auto-generated identity link of a committed stationary point."""
        with database.session() as session:
            stp = StationaryPointRow(geometry=water, calculation=calculation)
            session.add(stp)
            session.commit()
            yield session, stp.identity_links[0]

    def test_identity_cache_round_trip(
        self, identity_link: tuple[Session, IdentityStationaryLink]
    ) -> None:
        """`identity_cache` is stored compressed and read back as a dict."""
        session, link = identity_link
        cache = {"graph": [[0, 1], [0, 2]], "hash": "abc"}
        link.identity_cache = cache
        session.commit()
        session.expire_all()

        assert link.identity_cache == cache
        assert link.identity_id is not None
        raw = (
            session.connection()
            .execute(
                text(
                    "SELECT identity_cache FROM identity_stationary_link "
                    "WHERE identity_id = :id"
                ).bindparams(id=link.identity_id.hex)
            )
            .one()[0]
        )
        assert json.loads(zlib.decompress(raw)) == cache

    def test_identity_cache_in_place_change_persists(
        self, identity_link: tuple[Session, IdentityStationaryLink]
    ) -> None:
        """Setting a key of `identity_cache` in place is saved."""
        session, link = identity_link
        link.identity_cache = {"a": 1}
        session.commit()
        assert link.identity_cache is not None
        link.identity_cache["b"] = 2
        session.commit()
        session.expire_all()

        assert link.identity_cache == {"a": 1, "b": 2}

    def test_removing_identity_link_deletes_it(
        self, identity_link: tuple[Session, IdentityStationaryLink]
    ) -> None:
        """A link removed from its stationary point's links is deleted."""
        session, link = identity_link
        link.stationary.identity_links.remove(link)
        session.commit()

        assert (
            session.get(IdentityStationaryLink, (link.stationary_id, link.identity_id))
            is None
        )


class TestModelIntegration:
    """Integration tests for model interactions."""

    def test_geometry_with_multiple_results(
        self,
        database: Database,
        b3lyp: ModelRow,
        calculation: CalculationRow,
        hydrogen: GeometryRow,
    ) -> None:
        """Geometry can have multiple result types attached."""
        with database.session() as session:
            session.add_all([b3lyp, calculation, hydrogen])
            dim = 3 * hydrogen.atom_count
            ene = PropertyValueRow(
                geometry=hydrogen,
                calculation=calculation,
                property_kind_name=energy_property_kind.name,
                value=0.0,
            )
            grad = PropertyValueRow(
                geometry=hydrogen,
                calculation=calculation,
                property_kind_name=gradient_property_kind.name,
                value=np.zeros(dim),
            )
            hess = PropertyValueRow(
                geometry=hydrogen,
                calculation=calculation,
                property_kind_name=hessian_property_kind.name,
                value=np.zeros((dim, dim)),
            )
            session.add_all([ene, grad, hess])
            session.commit()

            assert len(hydrogen.properties) == 3

    def test_calculation_with_multiple_geometries(self, database: Database) -> None:
        """Calculation can be linked to multiple geometries."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom1 = GeometryRow(symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], spin=2)
            geom2 = GeometryRow(symbols=["C"], coordinates=[[0.1, 0.0, 0.0]], spin=2)
            session.add_all([geom1, geom2])
            session.flush()

            link1 = CalculationGeometryLink(
                calculation=calc, geometry_id=geom1.id, role=Role.INPUT
            )
            link2 = CalculationGeometryLink(
                calculation=calc, geometry_id=geom2.id, role=Role.OUTPUT
            )
            session.add_all([link1, link2])
            session.commit()

            assert len(calc.geometry_links) == 2

    def test_stationary_point_with_identity(self, database: Database) -> None:
        """Stationary point can be linked to an identity."""
        with database.session() as session:
            model = ModelRow(program="psi4", method="B3LYP")
            session.add(model)
            session.flush()

            calc = CalculationRow(model_id=model.id, calc_type="opt")
            session.add(calc)
            session.flush()

            geom = GeometryRow(symbols=["C"], coordinates=[[0.0, 0.0, 0.0]], spin=2)
            session.add(geom)
            session.flush()

            stat_pt = StationaryPointRow(geometry=geom, calculation=calc)
            # Add `stat_pt` before the query below, which triggers an
            # autoflush: flushing a transient object that was only attached
            # via a backref (not yet `session.add`-ed) raises a SAWarning.
            session.add(stat_pt)
            smiles_algorithm = session.exec(
                select(IdentityAlgorithmRow).where(
                    col(IdentityAlgorithmRow.name) == "rdkit_smiles"
                )
            ).one()
            identity = IdentityRow(algorithm_name=smiles_algorithm.name, value="C")
            session.add(identity)
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
            assert len(stat_pt.identity_links) >= 2
            assert link in stat_pt.identity_links
            assert identity.stationary_links == [link]
            assert link.stationary is stat_pt
            assert link.identity is identity
