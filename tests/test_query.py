"""Query module tests."""

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlmodel import col, select

from autostorage import (
    CalculationRow,
    Database,
    GeometryRow,
    IdentityAlgorithm,
    IdentityAlgorithmRow,
    Model,
    ModelHashAlgorithm,
    ModelHashAlgorithmRow,
    ModelRow,
    StationaryPointRow,
    hill_formula,
    minimal_hash,
    query,
    rdkit_inchi,
)

WATER_INCHI = "InChI=1S/H2O/h1H2"


@pytest.fixture
def database(tmp_path: Path) -> Generator[Database]:
    """Database with one regular and one pseudo water stationary point."""
    with Database(tmp_path / "test.db") as db:
        with db.session() as session:
            calc = CalculationRow(
                model=ModelRow(program="x", method="y"), calc_type="opt"
            )
            for shift, is_pseudo in ((0.0, False), (0.01, True)):
                # Shifted, since the same geometry can't be stored twice
                geo = GeometryRow(
                    symbols=["O", "H", "H"],
                    coordinates=[
                        [shift, 0.0, 0.0],
                        [shift, 0.76, 0.59],
                        [shift, -0.76, 0.59],
                    ],
                )
                session.add(
                    StationaryPointRow(
                        geometry=geo, calculation=calc, is_pseudo=is_pseudo
                    )
                )
            session.commit()
        yield db


@pytest.mark.parametrize("algorithm", [rdkit_inchi, "rdkit_inchi"])
def test_stationary_point_by_identity(
    database: Database, algorithm: IdentityAlgorithm | str
) -> None:
    """Stationary points can be selected by algorithm (or name) and value."""
    with database.session() as session:
        stmt = query.stationary_point_by_identity(algorithm, WATER_INCHI)
        stps = session.exec(stmt).all()

        assert len(stps) == 1
        assert not stps[0].is_pseudo


def test_stationary_point_by_identity_row(database: Database) -> None:
    """Stationary points can be selected by `IdentityAlgorithmRow`."""
    with database.session() as session:
        alg = session.exec(
            select(IdentityAlgorithmRow).where(
                col(IdentityAlgorithmRow.name) == "rdkit_inchi"
            )
        ).one()
        stmt = query.stationary_point_by_identity(alg, WATER_INCHI)

        assert len(session.exec(stmt).all()) == 1


def test_include_pseudo(database: Database) -> None:
    """`include_pseudo=True` selects both regular and pseudo stationary points."""
    with database.session() as session:
        stmt = query.stationary_point_by_identity(
            hill_formula, "H2O", include_pseudo=True
        )

        assert sorted(s.is_pseudo for s in session.exec(stmt).all()) == [False, True]


def test_no_match(database: Database) -> None:
    """Unknown identity values select nothing."""
    with database.session() as session:
        stmt = query.stationary_point_by_identity(rdkit_inchi, "InChI=1S/X")

        assert session.exec(stmt).all() == []


@pytest.fixture
def model_database(tmp_path: Path) -> Generator[Database]:
    """Database with two b3lyp/6-31g* models that differ in keywords, and an HF one."""
    with Database(tmp_path / "models.db") as db:
        with db.session() as session:
            session.add_all(
                [
                    ModelRow(
                        program="orca",
                        method="B3LYP",
                        basis="6-31G*",
                        keywords={"TightSCF": True},
                    ),
                    ModelRow(program="psi4", method="b3lyp", basis="6-31g*"),
                    ModelRow(program="psi4", method="hf", basis="sto-3g"),
                ]
            )
            session.commit()
        yield db


@pytest.mark.parametrize("algorithm", [minimal_hash, "minimal@1"])
def test_model_by_hash(
    model_database: Database, algorithm: ModelHashAlgorithm | str
) -> None:
    """Models sharing a minimal@1 value are all selected, by algorithm or name."""
    with model_database.session() as session:
        stmt = query.model_by_hash(algorithm, "b3lyp/6-31g*")
        models = session.exec(stmt).all()

        assert sorted(m.program for m in models) == ["orca", "psi4"]


def test_model_by_hash_from_model(model_database: Database) -> None:
    """A hash computed from an in-memory model finds the stored models."""
    value = minimal_hash.hash(Model(program="orca", method="B3LYP", basis="6-31G*"))
    with model_database.session() as session:
        stmt = query.model_by_hash(minimal_hash, value)

        assert len(session.exec(stmt).all()) == 2


def test_model_by_hash_row(model_database: Database) -> None:
    """Models can be selected by `ModelHashAlgorithmRow`."""
    with model_database.session() as session:
        alg = session.get(ModelHashAlgorithmRow, "minimal@1")
        assert alg is not None
        stmt = query.model_by_hash(alg, "hf/sto-3g")

        assert [m.program for m in session.exec(stmt).all()] == ["psi4"]


def test_model_by_hash_no_match(model_database: Database) -> None:
    """Unknown hash values, and the wrong algorithm, select nothing."""
    with model_database.session() as session:
        assert session.exec(query.model_by_hash("minimal@1", "mp2/cc-pvdz")).all() == []
        assert session.exec(query.model_by_hash("exact@1", "b3lyp/6-31g*")).all() == []
