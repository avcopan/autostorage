"""Tests for query utilities."""

from collections.abc import Iterator

import pytest
from sqlalchemy.exc import MultipleResultsFound, NoResultFound

from autostorage import Database, query
from autostorage.database import GeometryRow


@pytest.fixture
def database() -> Iterator[Database]:
    """In-memory database fixture."""
    db = Database(":memory:")

    try:
        yield db

    finally:
        db.close()


@pytest.fixture
def hydrogen1() -> GeometryRow:
    """Hydrogen geometry fixture."""
    return GeometryRow(
        symbols=["H"],
        coordinates=[[0, 1, 0]],  # ty:ignore[invalid-argument-type]
        charge=0,
        spin=0,
    )


@pytest.fixture
def hydrogen2() -> GeometryRow:
    """Hydrogen geometry fixture with swapped coordinates."""
    return GeometryRow(
        symbols=["H"],
        coordinates=[[1, 0, 0]],  # ty:ignore[invalid-argument-type]
        charge=0,
        spin=0,
    )


def test__first_match(
    database: Database, hydrogen1: GeometryRow, hydrogen2: GeometryRow
) -> None:
    """Test first match query."""
    database.add(hydrogen1)
    database.add(hydrogen2)

    assert hydrogen1.id != hydrogen2.id

    geo_partial: GeometryRow = GeometryRow.partial(symbols=hydrogen1.symbols)
    match = query.first_match(database, geo_partial)

    assert match
    assert match.id == hydrogen1.id


def test__all_matches(
    database: Database, hydrogen1: GeometryRow, hydrogen2: GeometryRow
) -> None:
    """Test all matches query."""
    database.add(hydrogen1)
    database.add(hydrogen2)

    assert hydrogen1.id != hydrogen2.id

    geo_partial: GeometryRow = GeometryRow.partial(symbols=hydrogen1.symbols)
    matches = query.all_matches(database, geo_partial)

    assert sorted([m.id for m in matches]) == sorted([hydrogen1.id, hydrogen2.id])


def test__one_match(
    database: Database, hydrogen1: GeometryRow, hydrogen2: GeometryRow
) -> None:
    """Test one match query."""
    geo_partial: GeometryRow = GeometryRow.partial(symbols=hydrogen1.symbols)

    with pytest.raises(NoResultFound):
        query.one_match(database, geo_partial)

    database.add(hydrogen1)

    match = query.one_match(database, geo_partial)

    assert match.id == hydrogen1.id

    database.add(hydrogen2)

    with pytest.raises(MultipleResultsFound):
        query.one_match(database, geo_partial)


def test__geometry_match(
    database: Database, hydrogen1: GeometryRow, hydrogen2: GeometryRow
) -> None:
    """Test geometry match query."""
    database.add(hydrogen1)
    database.add(hydrogen2)

    assert hydrogen1.id != hydrogen2.id

    match = query.geometry_match(database, hydrogen1)

    assert match
    assert match.id == hydrogen1.id
