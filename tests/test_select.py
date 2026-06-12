"""Test for select utilities."""

from collections.abc import Iterator

import pytest

from autostorage import Database, select
from autostorage.models import GeometryRow, TrajectoryGeometryLink, TrajectoryRow


@pytest.fixture
def trajectory() -> TrajectoryRow:
    """Fixture for ModelRow."""
    return TrajectoryRow()


@pytest.fixture
def water() -> GeometryRow:
    """Fixture for GeometryRow."""
    return GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=[[0, 0, 0], [0, 0, -1], [0, 0, 1]],  # ty:ignore[invalid-argument-type]
        charge=0,
        spin=0,
    )


@pytest.fixture
def link(trajectory: TrajectoryRow, water: GeometryRow) -> TrajectoryGeometryLink:
    """Fixture for TrajectoryGeometryLink."""
    return TrajectoryGeometryLink(trajectory=trajectory, geometry=water, index=[0])


@pytest.fixture
def database() -> Iterator[Database]:
    """In-memory database fixture."""
    db = Database(":memory:")

    try:
        yield db

    finally:
        db.close()


def test__matching_rows(database: Database, water: GeometryRow) -> None:
    """Test select matching rows."""
    database.add(water)
    stmt = select.matching_rows(GeometryRow.partial(charge=0))
    match = database.exec_one(stmt)
    assert match.id == water.id


def test__linked_rows(
    database: Database,
    trajectory: TrajectoryRow,
    water: GeometryRow,
    link: TrajectoryGeometryLink,
) -> None:
    """Test select linked rows."""
    database.add(link)
    stmt = select.linked_rows(
        row1=trajectory, row2=water, link=TrajectoryGeometryLink.partial()
    )
    match = database.exec_first(stmt)
    assert match == link
