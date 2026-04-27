"""Convenience methods for database."""

from collections.abc import Iterator

from autostore.types import SQLModelT


def row_to_dict(
    row: SQLModelT, *, exclude_defaults: bool = True, exclude_id: bool = False
) -> dict:
    """
    Dump model into a dictionary and optionally remove default fields.

    Parameters
    ----------
    row
        Database row.
    exclude_defaults
        If True, exclude default values from model dump.

    Returns
    -------
    dict
        row.model_dump() with or without default values.
    """
    data = row.model_dump(exclude_defaults=exclude_defaults)

    if "id" in data and exclude_id:
        del data["id"]

    return data


def verify_single_iteration(iterator: Iterator[SQLModelT]) -> SQLModelT:
    """
    Verify only a single object in Iterable return.

    Parameters
    ----------
    iterator
        Iterable sequence of database rows.

    Returns
    -------
    SQLModelT
        A single database row from iterator.

    Raises
    ------
    ValueError
        length of iterator is 0 or > 1.
    """
    calc_row = next(iterator, None)
    if not calc_row:
        msg = "iterator does not contain any database rows."
        raise ValueError(msg)

    if next(iterator, None):
        msg = "iterator contains more than one database row."
        raise ValueError(msg)

    return calc_row
