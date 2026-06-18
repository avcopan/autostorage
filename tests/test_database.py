"""Test for database module."""

from collections.abc import Iterator

import pytest
from sqlalchemy.exc import IntegrityError, NoResultFound

from autostorage import Database, select
from autostorage.database import ModelRow


@pytest.fixture
def database() -> Iterator[Database]:
    """In-memory database fixture."""
    db = Database(":memory:")

    try:
        yield db

    finally:
        db.close()


@pytest.fixture
def model() -> ModelRow:
    """Fixture for ModelRow."""
    return ModelRow(
        program="ORCA",
        program_version="6.1.1",
        calc_type="test",
        method="b3lyp",
        basis="def2-SVP",
    )


def test__add(database: Database, model: ModelRow) -> None:
    """Test add to database."""
    database.add(model)

    assert model.id


def test__invalid_add(database: Database, model: ModelRow) -> None:
    """Test invalid add to database."""
    model.program = None  # ty:ignore[invalid-assignment]
    with pytest.raises(IntegrityError):
        database.add(model)


def test__delete(database: Database, model: ModelRow) -> None:
    """Test delete from database."""
    database.add(model)
    stmt = select.matching_rows(model)
    match = database.exec_one(stmt)
    assert match

    database.delete(model)
    stmt = select.matching_rows(model)
    with pytest.raises(NoResultFound):
        match = database.exec_one(stmt)


def test__get(database: Database, model: ModelRow) -> None:
    """Test get from database."""
    database.add(model)
    assert model.id

    match = database.get(ModelRow, model.id)
    assert match == model


def test__invalid_get(database: Database) -> None:
    """Test invalid get from database."""
    with pytest.raises(LookupError):
        database.get(ModelRow, 679)


def test__exec_first(database: Database, model: ModelRow) -> None:
    """Test exec first from database."""
    database.add(model)
    stmt = select.matching_rows(model)
    match = database.exec_first(stmt)
    assert match


def test__exec_one(database: Database, model: ModelRow) -> None:
    """Test exec one from database."""
    database.add(model)
    stmt = select.matching_rows(model)
    match = database.exec_one(stmt)
    assert match


def test__invalid_exec_one(database: Database, model: ModelRow) -> None:
    """Test delete and invalid exec one from database."""
    stmt = select.matching_rows(model)
    with pytest.raises(NoResultFound):
        database.exec_one(stmt)


def test__exec_all(database: Database, model: ModelRow) -> None:
    """Test exec all from database."""
    database.add(model)
    partial = ModelRow.partial()
    stmt = select.matching_rows(partial)
    for match in database.exec_all(stmt):
        assert match == model
