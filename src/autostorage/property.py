"""Property kind registry with default definitions."""

from typing import ClassVar, Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict

from .models import GeometryRow

__all__ = [
    "PropertyKind",
    "PropertyKindRegistry",
    "PropertyValidationProtocol",
    "energy_property_kind",
    "gradient_property_kind",
    "hessian_property_kind",
]


@runtime_checkable
class PropertyValidationProtocol(Protocol):
    """Protocol for property value validation functions."""

    def __call__(self, value: npt.NDArray, geo_row: GeometryRow) -> bool:
        """Return whether `value` has a valid shape for a property of `geo_row`."""
        ...


class PropertyKind(BaseModel):
    """A registered kind of property.

    Attributes:
        name: Unique property kind name (primary key of `PropertyKindRow`).
        validation_fn: Function checking that a value has the expected shape.
        dtype: NumPy dtype used to store values of this kind.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    validation_fn: PropertyValidationProtocol
    dtype: type[np.floating] = np.float64


class PropertyKindRegistry:
    """Central registry of all known property kinds."""

    property_kinds: ClassVar[list[PropertyKind]] = []

    @classmethod
    def register(
        cls,
        name: str,
        validation_fn: PropertyValidationProtocol,
        dtype: type[np.floating] = np.float64,
    ) -> PropertyKind:
        """Create and register a property kind.

        Raises:
            ValueError: If a property kind named `name` is already registered.
        """
        if any(name == p.name for p in cls.property_kinds):
            msg = f"Property kind {name!r} is already registered."
            raise ValueError(msg)
        property_kind = PropertyKind(
            name=name, validation_fn=validation_fn, dtype=dtype
        )
        cls.property_kinds.append(property_kind)
        return property_kind

    @classmethod
    def get(cls, name: str) -> PropertyKind:
        """Get a registered property kind by name.

        Raises:
            KeyError: If no property kind named `name` is registered.
        """
        try:
            return next(p for p in cls.property_kinds if p.name == name)
        except StopIteration:
            available = ", ".join(sorted(p.name for p in cls.property_kinds))
            msg = f"Unknown property kind {name!r}. Available: {available}"
            raise KeyError(msg) from None


def energy_validation_fn(value: npt.NDArray, geo_row: GeometryRow) -> bool:  # noqa: ARG001
    """Validate a scalar (or length-1) `energy` value."""
    return value.shape in {(), (1,)}


energy_property_kind = PropertyKindRegistry.register(
    name="energy", validation_fn=energy_validation_fn
)
"""Energy: a scalar, stored as float64."""


def gradient_validation_fn(value: npt.NDArray, geo_row: GeometryRow) -> bool:
    """Validate a ``(3N,)`` or ``(N, 3)`` `gradient` value."""
    natoms = geo_row.atom_count
    return value.shape in {(3 * natoms,), (natoms, 3)}


gradient_property_kind = PropertyKindRegistry.register(
    name="gradient", validation_fn=gradient_validation_fn
)
"""Gradient: shape ``(3N,)`` or ``(N, 3)``, stored as float64."""


def hessian_validation_fn(value: npt.NDArray, geo_row: GeometryRow) -> bool:
    """Validate a ``(3N, 3N)`` `hessian` value."""
    ndim = 3 * geo_row.atom_count
    return value.shape == (ndim, ndim)


hessian_property_kind = PropertyKindRegistry.register(
    name="hessian", validation_fn=hessian_validation_fn, dtype=np.float32
)
"""Hessian: shape ``(3N, 3N)``, stored as float32."""
