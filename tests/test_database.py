"""Test for database module."""

import pytest
from numpy.random import Generator
from sqlalchemy.exc import IntegrityError

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


def test__query(database: Database, model_row: ModelRow) -> None:
    """Test chainable query builder."""
    database.add(model_row)
    database.commit()

    match = database.query(ModelRow).where(ModelRow.program == "ORCA").first()
    assert match == model_row

    assert database.query(ModelRow).where(ModelRow.program == "ORCA").one() == model_row

    assert list(database.query(ModelRow).where(ModelRow.program == "ORCA").all())

    assert (
        database.query(ModelRow).where(ModelRow.program == "nonexistent").first()
        is None
    )


def test__query_offset_and_distinct(database: Database) -> None:
    """Test offset and distinct on the chainable query builder."""
    rows = [
        ModelRow(program="ORCA", method="b3lyp", basis=f"basis{i}") for i in range(3)
    ]
    for row in rows:
        database.add(row)
    database.commit()

    ordered = list(
        database.query(ModelRow)
        .order_by(ModelRow.basis)  # ty:ignore[invalid-argument-type]
        .offset(1)
        .all()
    )
    assert [r.basis for r in ordered] == ["basis1", "basis2"]

    programs = list(database.query(ModelRow).distinct().all())
    assert {p.program for p in programs} == {"ORCA"}


def test__merge_commits(database: Database, model_row: ModelRow) -> None:
    """Test that merge() (and therefore BaseRow.save()) commits immediately."""
    merged = model_row.save(database)
    assert merged.id

    # A rollback after save() must not undo it, since merge() already committed.
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
