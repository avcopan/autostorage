"""Test for database module."""

import pytest
from sqlalchemy.exc import IntegrityError, NoResultFound

from autostorage import Database
from autostorage.database import ModelRow, Select, SelectStatement


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

    # Violate hash uniqueness
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
    with pytest.raises(NoResultFound):
        database.exec_one(orca_model_statement)


def test__exec_all(
    database: Database, model_row: ModelRow, orca_model_statement: SelectStatement
) -> None:
    """Test exec all from database."""
    database.add(model_row)
    for match in database.exec_all(orca_model_statement):
        assert match
