"""Helper and class method mixin for partially initialized RowModels."""

from typing import Annotated, Any

from pydantic import BaseModel, Field, create_model
from sqlmodel import SQLModel


def make_fields_optional(model_cls: type[BaseModel]) -> type[BaseModel]:
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

    return create_model(
        f"{model_cls.__name__}Optional",
        __base__=SQLModel,
        __module__=model_cls.__module__,
        **new_fields,
    )


class PartialMixin:
    """Mixin for Partial method on SQLModel classes."""

    @classmethod
    def partial(cls: type[SQLModel], **attrs: Any) -> SQLModel:  # noqa: ANN401
        """Return the model with partial assignment of required fields."""
        optional_model = make_fields_optional(cls)
        # Check valid fields
        invalid = set(attrs) - set(cls.model_fields)
        if invalid:
            msg = f" Unexpected fields in {cls.__name__}.partial(): {sorted(invalid)}"
            raise ValueError(msg)
        validated = optional_model(**attrs)
        return cls.model_construct(**validated.model_dump(exclude_unset=True))
