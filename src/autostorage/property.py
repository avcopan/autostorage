"""Property kind registry with default definitions."""

from typing import ClassVar, Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt
import pint
from autogeom import ureg
from pydantic import BaseModel, ConfigDict, field_validator

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
        units: Native units, as a `pint` unit string; values are stored in these.
        dtype: NumPy dtype used to store values of this kind.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    validation_fn: PropertyValidationProtocol
    units: str
    dtype: type[np.floating] = np.float64

    @field_validator("units")
    @classmethod
    def _check_units(cls, units: str) -> str:
        """Check that `units` is a unit `pint` can parse."""
        try:
            ureg.Unit(units)
        except (pint.UndefinedUnitError, AttributeError, TypeError, ValueError) as err:
            msg = f"Invalid units {units!r}: {err}"
            raise ValueError(msg) from err
        return units

    def to_native(self, value: object) -> npt.NDArray:
        """Return `value` as an array in native units and the storage dtype.

        A `pint.Quantity` is converted to `units`, including molar quantities (e.g.
        kcal/mol for Hartree), which are scaled by Avogadro's constant. Any other
        value is assumed to be in `units` already.

        Raises:
            ValueError: If `value` has incompatible units, or is not numeric.
        """
        if isinstance(value, pint.Quantity):
            value = _magnitude_as(value, self.units)
        try:
            return np.asarray(value, dtype=self.dtype)
        except (TypeError, ValueError) as err:
            # Raised for ragged/inhomogeneous or non-numeric values
            msg = "Expected a numeric array."
            raise ValueError(msg) from err

    def from_native(self, value: npt.ArrayLike, units: str) -> npt.NDArray:
        """Convert a stored `value` from native units to `units`.

        Molar `units` (e.g. kcal/mol for Hartree) are handled as in `to_native`.

        Raises:
            ValueError: If `units` is incompatible with the native units.

        Examples:
            >>> print(energy_property_kind.from_native(-1.0, "kcal/mol").round(2))
            -627.51
        """
        return np.asarray(_magnitude_as(self.quantity(value), units))

    def quantity(self, value: npt.ArrayLike) -> pint.Quantity:
        """Attach native units to a stored `value`.

        Plain pint conversions don't handle molar units; use `from_native` for those.

        Examples:
            >>> print(round(energy_property_kind.quantity(-1.0).m_as("eV"), 4))
            -27.2114
        """
        return ureg.Quantity(np.asarray(value), self.units)


def _magnitude_as(quantity: pint.Quantity, units: str) -> object:
    """Return the magnitude of `quantity` in `units`, converting molar to per-particle.

    Raises:
        ValueError: If `quantity` is incompatible with `units`, with or without a
            factor of Avogadro's constant.
    """
    avogadro = quantity._REGISTRY.avogadro_constant  # noqa: SLF001
    for candidate in (quantity, quantity / avogadro, quantity * avogadro):
        try:
            return candidate.m_as(units)
        except pint.DimensionalityError:
            continue
    msg = f"Expected units compatible with {units!r} but got {quantity.units:~}."
    raise ValueError(msg)


class PropertyKindRegistry:
    """Central registry of all known property kinds."""

    property_kinds: ClassVar[list[PropertyKind]] = []

    @classmethod
    def register(
        cls,
        name: str,
        validation_fn: PropertyValidationProtocol,
        units: str,
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
            name=name, validation_fn=validation_fn, units=units, dtype=dtype
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
    name="energy", validation_fn=energy_validation_fn, units="hartree"
)
"""Energy: a scalar in Hartree, stored as float64."""


def gradient_validation_fn(value: npt.NDArray, geo_row: GeometryRow) -> bool:
    """Validate a ``(3N,)`` or ``(N, 3)`` `gradient` value."""
    natoms = geo_row.atom_count
    return value.shape in {(3 * natoms,), (natoms, 3)}


gradient_property_kind = PropertyKindRegistry.register(
    name="gradient", validation_fn=gradient_validation_fn, units="hartree / bohr"
)
"""Gradient: shape ``(3N,)`` or ``(N, 3)`` in Hartree/Bohr, stored as float64."""


def hessian_validation_fn(value: npt.NDArray, geo_row: GeometryRow) -> bool:
    """Validate a ``(3N, 3N)`` `hessian` value."""
    ndim = 3 * geo_row.atom_count
    return value.shape == (ndim, ndim)


hessian_property_kind = PropertyKindRegistry.register(
    name="hessian",
    validation_fn=hessian_validation_fn,
    units="hartree / bohr ** 2",
    dtype=np.float32,
)
"""Hessian: shape ``(3N, 3N)`` in Hartree/Bohr², stored as float32."""
