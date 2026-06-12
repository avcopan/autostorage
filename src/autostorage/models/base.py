"""Helper and class method mixin for partially initialized RowModels."""

import operator
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Self, TypeVar, cast

from pydantic import BaseModel, Field, create_model
from sqlmodel import SQLModel


def make_fields_optional[ModelT: BaseModel](model_cls: type[ModelT]) -> type[ModelT]:
    """Convert RowModel to an OptionalModel retaining original fields and typing."""
    new_fields = {}

    relationships = getattr(model_cls, "__sqlmodel_relationships__", {})

    for f_name, f_info in model_cls.model_fields.items():
        # Skip relationships
        if f_name in relationships:
            continue

        f_dct = f_info.asdict()

        # Reset default factories to allow for None in OptionalModel
        attrs = dict(f_dct["attributes"])
        attrs.pop("default", None)
        attrs.pop("default_factory", None)

        new_fields[f_name] = (
            Annotated[
                f_dct["annotation"] | None,  # noqa: F821
                *f_dct["metadata"],
                Field(**attrs),
            ],
            None,
        )

    return cast(
        "type[ModelT]",
        create_model(
            f"{model_cls.__name__}Optional",
            __module__=model_cls.__module__,
            __config__=model_cls.model_config,
            **new_fields,
        ),
    )


class PartialMixin:
    """Mixin for Partial method on SQLModel classes."""

    @classmethod
    def partial(cls: type[SQLModel], **attrs: Any) -> Self:  # noqa: ANN401
        """Return the model with partial assignment of required fields."""
        optional_model = make_fields_optional(cls)
        # Check valid fields
        invalid = set(attrs) - set(cls.model_fields)

        if invalid:
            msg = f" Unexpected fields in {cls.__name__}.partial(): {sorted(invalid)}"
            raise ValueError(msg)
        validated = optional_model(**attrs)

        data = validated.model_dump(
            exclude_unset=True,
        )

        return cast(
            "Self",
            cls.model_construct(_fields_set=set(attrs.keys()), **data),
        )


class ComparisonMixin(BaseModel):  # noqa: PLW1641
    """Mixin for defining Comparison behavior on SQLModel classes."""

    _field_comparisons: ClassVar[dict[str, Callable[[Any, Any], bool]] | None] = None

    def __eq__(self, other: object) -> bool:
        """Compare equivalency between self and other."""
        comps = self.__class__._field_comparisons or {}
        comps["id"] = comps.get("id", lambda _, __: True)

        if type(self) is not type(other):
            return False

        for field in type(self).model_fields:
            val_self = getattr(self, field, None)
            val_other = getattr(other, field, None)

            comp = comps.get(field, operator.eq)

            if not comp(val_self, val_other):
                return False

        return True


class BaseRow(SQLModel, PartialMixin, ComparisonMixin):
    """Base model for AutoStorage SQL rows."""


BaseRowT = TypeVar("BaseRowT", bound=BaseRow)
