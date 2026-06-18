"""Convenient querying methods."""

from collections.abc import Iterator

from automatics import geom

from . import select
from .database import Database
from .models import GeometryRow
from .models.base import BaseRowT


def first_match(db: Database, row: BaseRowT) -> BaseRowT | None:
    """Return matching row if found."""
    stmt = select.matching_rows(row)
    return db.exec_first(stmt)


def all_matches(db: Database, row: BaseRowT) -> Iterator[BaseRowT]:
    """Yield matching rows if found."""
    stmt = select.matching_rows(row)
    yield from db.exec_all(stmt)


def one_match(db: Database, row: BaseRowT) -> BaseRowT:
    """Return matching row if found."""
    stmt = select.matching_rows(row)
    return db.exec_one(stmt)


def geometry_match(db: Database, geo: GeometryRow) -> GeometryRow | None:
    """Return matching geometry if found."""
    geo_hash = geo.hash or geom.geometry_hash(geo)
    geo_partial = GeometryRow.partial(hash=geo_hash)
    return first_match(db, geo_partial)
