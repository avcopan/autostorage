"""Autostorage exceptions."""

from typing import Self

from sqlmodel import SQLModel

__all__ = ["MissingPrimaryKeyError", "ResultShapeError"]


class ResultShapeError(Exception):
    """Raise when a result violates expected shape."""

    def __init__(
        self: Self, model: SQLModel, actual: tuple[int, ...], expected: tuple[int, ...]
    ) -> None:
        """Initialize exception."""
        class_name = model.__class__.__name__
        msg = f"{class_name} shape ({actual}) does not match expected ({expected})."
        super().__init__(msg)


class MissingPrimaryKeyError(Exception):
    """Raise when primary keys weren't provided to a query method."""

    def __init__(self: Self, rows: list[SQLModel]) -> None:
        row_ids = [
            f"{row.__class__.__name__}: {getattr(row, 'id', None)}" for row in rows
        ]
        msg = (
            f"Cannot perform operation using unpersisted database instance(s).\n"
            f"Try Database.add(row) or Database.merge(row) before querying.\n"
            f"({','.join(row_ids)})."
        )
        super().__init__(msg)
