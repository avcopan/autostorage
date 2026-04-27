"""Test for database module."""

import pytest
from sqlalchemy.exc import IntegrityError, InvalidRequestError

from autostore import CalculationGeometryLink, CalculationRow, Database
from autostore.utils import row_to_dict, verify_single_iteration


def test__add(blank_database: Database, calc_row: CalculationRow) -> None:
    """Test add to database."""
    blank_database.add(calc_row)
    assert calc_row.id


def test__invalid_add(blank_database: Database, calc_row: CalculationRow) -> None:
    """Test invalid add to database."""
    calc_row.program = None  # ty:ignore[invalid-assignment]
    with pytest.raises(IntegrityError):
        blank_database.add(calc_row)


def test__find(calc_geo_database: Database, calc_row: CalculationRow) -> None:
    """Test get from database."""
    found_rows = calc_geo_database.find(calc_row, eager_load=True, exclude_id=True)
    found_row = verify_single_iteration(found_rows)
    assert found_row.id
    assert found_row.geometry_links


def test__blank_find(blank_database: Database, calc_row: CalculationRow) -> None:
    """Test blank find from database."""
    calc_rows = blank_database.find(calc_row)
    with pytest.raises(ValueError):  # noqa: PT011
        verify_single_iteration(calc_rows)


def test__delete(calc_geo_database: Database, calc_row: CalculationRow) -> None:
    """Test delete from database."""
    calc_geo_database.delete(calc_row)
    calc_rows = calc_geo_database.find(calc_row, eager_load=True)
    assert not next(calc_rows, None)
    # Check for successful cascade delete
    calc_geo_links = calc_geo_database.find(CalculationGeometryLink.partial())
    assert not next(calc_geo_links, None)


def test__invalid_delete(blank_database: Database) -> None:
    """Test invalid delete from database."""
    with pytest.raises(InvalidRequestError):
        blank_database.delete(CalculationRow.partial())


def test__find_or_add(calc_geo_database: Database, calc_row: CalculationRow) -> None:
    """Test find or add row in database."""
    found_rows1 = calc_geo_database.find_or_add(calc_row, exclude_id=True)
    found_row1 = verify_single_iteration(found_rows1)
    assert found_row1.id == calc_row.id

    calc_row2 = CalculationRow(**row_to_dict(calc_row, exclude_id=True))
    calc_geo_database.add(calc_row2)
    assert calc_row2.id != found_row1.id

    # Assert that found_rows2 is not singular
    found_rows2 = calc_geo_database.find_or_add(
        CalculationRow.partial(), exclude_id=False
    )
    with pytest.raises(ValueError):  # noqa: PT011
        verify_single_iteration(found_rows2)
