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
    ModelRow,
    StationaryPointRow,
    hill_formula,
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
            for is_pseudo in (False, True):
                geo = GeometryRow(
                    symbols=["O", "H", "H"],
                    coordinates=[
                        [0.0, 0.0, 0.0],
                        [0.0, 0.76, 0.59],
                        [0.0, -0.76, 0.59],
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
