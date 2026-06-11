"""Test for database module."""

import pytest
from sqlalchemy.exc import IntegrityError, NoResultFound

from autostorage import Calculation, Database
from autostorage.utils import select
from autostorage.models import CalculationRow


def test__add(database: Database, calc: Calculation) -> None:
    """Test add to database."""
    calc.program = "test"

    calc_row = CalculationRow.from_calculation(calc)
    database.add(calc_row)

    assert calc_row.id


def test__invalid_add(database: Database, calc_row: CalculationRow) -> None:
    """Test invalid add to database."""
    calc_row.program = None  # ty:ignore[invalid-assignment]
    with pytest.raises(IntegrityError):
        database.add(calc_row)


def test__exec_first(database: Database, calc_row: CalculationRow) -> None:
    """Test exec first from database."""
    stmt = select.matching_rows(calc_row)
    database.exec_first(stmt)
    assert calc_row.id


def test__exec_one(database: Database, calc_row: CalculationRow) -> None:
    """Test exec one from database."""
    stmt = select.matching_rows(calc_row)
    database.exec_one(stmt)
    assert calc_row is not None


def test__invalid_exec_one(database: Database, calc_row: CalculationRow) -> None:
    """Test delete and invalid exec one from database."""
    database.delete(calc_row)
    stmt = select.matching_rows(calc_row)
    with pytest.raises(NoResultFound):
        database.exec_one(stmt)


def test__exec_all(database: Database) -> None:
    """Test exec all from database."""
    partial = CalculationRow.partial()
    stmt = select.matching_rows(partial)
    for calc_row in database.exec_all(stmt):
        assert isinstance(calc_row, CalculationRow)
