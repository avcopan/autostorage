"""Test for database module."""

import pytest
from numpy.random import Generator
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from autostorage import (
    CalculationGeometryLink,
    CalculationRow,
    Database,
    GeometryRow,
    GradientRow,
)
from autostorage.database import ModelRow, Select, SelectStatement
from autostorage.exc import ResultShapeError


def test__add(database: Database, model_row: ModelRow) -> None:
    """Test add to database."""
    database.add(model_row)
    database.commit()

    assert model_row.id


def test__invalid_add(database: Database, model_row: ModelRow) -> None:
    """Test invalid add to database."""
    model_row2 = model_row.model_copy(deep=True)

    database.add(model_row)
    database.commit()

    # Violate ModelRow's (program, program_version, method, basis) unique constraint
    database.add(model_row2)
    with pytest.raises(IntegrityError):
        database.commit()


def test__get(database: Database, model_row: ModelRow) -> None:
    """Test get from database."""
    database.add(model_row)
    database.commit()
    assert model_row.id

    match = database.get(ModelRow, model_row.id)
    assert match == model_row


def test__invalid_get(database: Database) -> None:
    """Test invalid get from database."""
    with pytest.raises(LookupError):
        database.get(ModelRow, 679)


def test__get_or_none_returns_row_or_none(
    database: Database, model_row: ModelRow
) -> None:
    """Test get_or_none returns the row on a hit and None on a miss."""
    database.add(model_row)
    database.commit()
    assert model_row.id

    assert database.get_or_none(ModelRow, model_row.id) == model_row
    assert database.get_or_none(ModelRow, 679) is None


def test__add_all(database: Database) -> None:
    """Test add_all stages multiple rows for the next flush/commit."""
    rows = [ModelRow(program="orca", method="xtb", basis=f"basis{i}") for i in range(3)]
    database.add_all(rows)
    database.commit()

    assert all(row.id is not None for row in rows)
    assert len({row.id for row in rows}) == len(rows)


def test__delete(database: Database, model_row: ModelRow) -> None:
    """Test delete from database."""
    database.add(model_row)
    database.commit()
    assert model_row.id

    database.delete(model_row)
    database.commit()
    with pytest.raises(LookupError, match=r"with row_id = 1 not found."):
        database.get(ModelRow, model_row.id)


@pytest.fixture
def orca_model_statement() -> SelectStatement:
    """Fixture for Statement."""
    return Select(ModelRow).where(ModelRow.program == "ORCA")


def test__exec_first(
    database: Database,
    model_row: ModelRow,
    orca_model_statement: SelectStatement,
) -> None:
    """Test exec first from database."""
    database.add(model_row)
    match = database.exec_first(orca_model_statement)
    assert match


def test__exec_one(
    database: Database, model_row: ModelRow, orca_model_statement: SelectStatement
) -> None:
    """Test exec one from database."""
    database.add(model_row)
    match = database.exec_one(orca_model_statement)
    assert match


def test__invalid_exec_one(
    database: Database, orca_model_statement: SelectStatement
) -> None:
    """Test delete and invalid exec one from database."""
    with pytest.raises(LookupError):
        database.exec_one(orca_model_statement)


def test__exec_all(
    database: Database, model_row: ModelRow, orca_model_statement: SelectStatement
) -> None:
    """Test exec all from database."""
    database.add(model_row)
    for match in database.exec_all(orca_model_statement):
        assert match


def test__exists_true_and_false(
    database: Database, model_row: ModelRow, orca_model_statement: SelectStatement
) -> None:
    """Test exists() returns True for a match and False otherwise."""
    database.add(model_row)
    database.commit()

    assert database.exists(orca_model_statement) is True
    missing_stmt = select(ModelRow).where(ModelRow.program == "nonexistent")
    assert database.exists(missing_stmt) is False


def test__select_statement_chaining(database: Database, model_row: ModelRow) -> None:
    """Test that native SQLModel statement chaining works through exec_*."""
    database.add(model_row)
    database.commit()

    stmt = select(ModelRow).where(ModelRow.program == "ORCA")
    assert database.exec_first(stmt) == model_row
    assert database.exec_one(stmt) == model_row
    assert list(database.exec_all(stmt))

    missing_stmt = select(ModelRow).where(ModelRow.program == "nonexistent")
    assert database.exec_first(missing_stmt) is None


def test__select_statement_offset_and_distinct(database: Database) -> None:
    """Test offset and distinct on a plain select() statement."""
    rows = [
        ModelRow(program="ORCA", method="b3lyp", basis=f"basis{i}") for i in range(3)
    ]
    for row in rows:
        database.add(row)
    database.commit()

    ordered_stmt = select(ModelRow).order_by(ModelRow.basis).offset(1)
    ordered = list(database.exec_all(ordered_stmt))
    assert [r.basis for r in ordered] == ["basis1", "basis2"]

    distinct_stmt = select(ModelRow).distinct()
    programs = list(database.exec_all(distinct_stmt))
    assert {p.program for p in programs} == {"ORCA"}


def test__merge_commits(database: Database, model_row: ModelRow) -> None:
    """Test that merge() commits immediately."""
    merged = database.merge(model_row)
    assert merged.id

    # A rollback after merge() must not undo it, since merge() already committed.
    database._session.rollback()  # noqa: SLF001
    assert database.get(ModelRow, merged.id) == merged


def test__session_rolls_back_on_generic_error(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    calc_geo_link: CalculationGeometryLink,
    rng: Generator,
) -> None:
    """A non-IntegrityError failure rolls back, leaving the session usable."""
    database.add(calculation_row)
    database.add(geometry_row)
    database.add(calc_geo_link)
    database.add(
        GradientRow(
            calculation=calculation_row,
            geometry=geometry_row,
            value=rng.uniform(size=2),
        )
    )

    with pytest.raises(ResultShapeError):
        database.commit()

    # The session must still be usable for subsequent, unrelated operations.
    unrelated = ModelRow(program="ORCA", method="b3lyp")
    database.add(unrelated)
    database.commit()
    assert unrelated.id


def test__link_table_reverse_lookup_indexes_exist(database: Database) -> None:
    """Test that the trailing column of each composite-PK link table is indexed.

    The composite primary key on each of these tables only serves lookups keyed
    by its leading column; each also needs its own index for the other direction.
    """
    expected = {
        "calculation_geometry_link": "calculation_id",
        "calculation_trajectory_link": "calculation_id",
        "trajectory_geometry_link": "trajectory_id",
        "stationary_identity_link": "identity_id",
        "stationary_stage_link": "stage_id",
        "step_validation_link": "validation_id",
    }
    inspector = inspect(database.engine)
    for table, column in expected.items():
        indexed_columns = {
            name for idx in inspector.get_indexes(table) for name in idx["column_names"]
        }
        assert column in indexed_columns
