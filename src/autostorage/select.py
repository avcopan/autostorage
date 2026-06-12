"""SELECT statement factories for SQL querying."""

from sqlmodel import select
from sqlmodel.sql.expression import SelectOfScalar

from .models.base import BaseRow, BaseRowT


def matching_rows(row: BaseRowT) -> SelectOfScalar[BaseRowT]:
    """
    Write a statement for matching rows.

    Queried fields are dictated by the model_fields_set attribute in Pydantic.

    Parameters
    ----------
    row
        Database row instance.

    Returns
    -------
    SQLModel select statement.
    """
    data = row.model_dump(include=row.model_fields_set)

    model = type(row)
    statement = select(model)

    for k, v in data.items():
        statement = statement.where(getattr(model, k) == v)

    return statement


def linked_rows[T1: BaseRow, T2: BaseRow, T3: BaseRow](
    row1: T1, row2: T2, link: T3
) -> SelectOfScalar[T3]:
    """
    Select rows connecting two model instances.

    Parameters
    ----------
    row1
        First row instance.
    row2
        Second row instance.
    link
        Link model instance connecting row1 with row2.

    Returns
    -------
    SQLModel select statement.
    """
    statement = select(type(link)).join(type(row1)).join(type(row2))

    for k, v in link.model_dump(include=link.model_fields_set).items():
        statement = statement.where(getattr(type(link), k) == v)

    for k, v in row1.model_dump(include=row1.model_fields_set).items():
        statement = statement.where(getattr(type(row1), k) == v)

    for k, v in row2.model_dump(include=row2.model_fields_set).items():
        statement = statement.where(getattr(type(row2), k) == v)

    return statement
