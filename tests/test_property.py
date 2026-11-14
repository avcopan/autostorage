"""Property module tests."""

import numpy as np
import pytest
from autogeom import ureg

from autostorage.property import (
    PropertyKind,
    PropertyKindRegistry,
    energy_property_kind,
    hessian_property_kind,
)


class TestPropertyKindRegistry:
    """Tests for PropertyKindRegistry."""

    def test_get(self) -> None:
        """A registered property kind is returned by name."""
        assert PropertyKindRegistry.get("energy") is energy_property_kind

    def test_get_unknown(self) -> None:
        """Looking up an unregistered name raises a KeyError listing the options."""
        with pytest.raises(KeyError, match=r"Unknown property kind 'nope'.*energy"):
            PropertyKindRegistry.get("nope")

    def test_register_duplicate(self) -> None:
        """Registering an existing name raises a ValueError."""
        with pytest.raises(ValueError, match="already registered"):
            PropertyKindRegistry.register(
                "energy",
                validation_fn=energy_property_kind.validation_fn,
                units="hartree",
            )


class TestPropertyKind:
    """Tests for PropertyKind."""

    def test_invalid_units(self) -> None:
        """Units that pint cannot parse are rejected."""
        with pytest.raises(ValueError, match="Invalid units 'nope'"):
            PropertyKind(
                name="x",
                validation_fn=energy_property_kind.validation_fn,
                units="nope",
            )

    def test_to_native_plain_value(self) -> None:
        """Values without units are assumed to be in native units."""
        value = hessian_property_kind.to_native([[1, 2], [3, 4]])
        assert value.dtype == np.float32
        np.testing.assert_array_equal(value, [[1, 2], [3, 4]])

    def test_to_native_quantity(self) -> None:
        """Quantities are converted to native units."""
        value = energy_property_kind.to_native(ureg.Quantity(1.0, "eV"))
        assert float(value) == pytest.approx(1 / 27.211386245988)

    def test_to_native_incompatible_units(self) -> None:
        """Quantities with incompatible units are rejected."""
        with pytest.raises(ValueError, match="compatible with 'hartree'"):
            energy_property_kind.to_native(ureg.Quantity(1.0, "bohr"))

    def test_to_native_non_numeric(self) -> None:
        """Non-numeric values are rejected."""
        with pytest.raises(ValueError, match="numeric array"):
            energy_property_kind.to_native("abc")

    def test_quantity(self) -> None:
        """Stored values are returned with native units attached."""
        quantity = energy_property_kind.quantity(np.float64(-1.0))
        assert quantity.units == ureg.hartree
        assert quantity.m_as("eV") == pytest.approx(-27.211386245988)

    def test_kcal_per_mol_round_trip(self) -> None:
        """Values convert to and from kcal/mol, including derivatives."""
        hartree_in_kcal_per_mol = 627.509474
        assert float(
            energy_property_kind.to_native(ureg.Quantity(1.0, "kcal/mol"))
        ) == pytest.approx(1 / hartree_in_kcal_per_mol)
        assert float(
            energy_property_kind.from_native(1.0, "kcal/mol")
        ) == pytest.approx(hartree_in_kcal_per_mol)

        units = "kcal/mol/angstrom**2"
        value = hessian_property_kind.to_native(ureg.Quantity(np.eye(3), units))
        np.testing.assert_allclose(
            hessian_property_kind.from_native(value, units), np.eye(3), rtol=1e-6
        )

    def test_from_native_incompatible_units(self) -> None:
        """Converting to incompatible units is rejected."""
        with pytest.raises(ValueError, match="compatible with 'bohr'"):
            energy_property_kind.from_native(1.0, "bohr")
