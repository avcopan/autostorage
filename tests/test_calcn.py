"""Tests for calcn module."""

import pytest

from autostorage import Calculation
from autostorage.calcn import (
    calculation_hash,
    hash_from_dict,
    project,
    project_keywords,
)
from autostorage.calcn.registry import HashRegistry, hash_full, hash_minimal


def test__deterministic_hash() -> None:
    """Test that the hash is deterministic."""
    data = {"a": "b", "c": "d"}
    assert hash_from_dict(data) == hash_from_dict({"c": "d", "a": "b"})


def test__project_flattened() -> None:
    """Test that the projection of flattened keywords produces the same hash."""
    keywords = {"dft": "b3lyp", "basis": "6-31g", "extra": "ignore"}
    template = {"dft": None, "basis": None}
    assert project_keywords(keywords, template) == {"dft": "b3lyp", "basis": "6-31g"}


def test__project_keywords_nested() -> None:
    """Test that the projection of nested keywords produces the same hash."""
    keywords = {"opt": {"maxiter": 100, "tol": 1e-6}, "other": 1}
    template = {"opt": {"maxiter": None}}
    assert project_keywords(keywords, template) == {"opt": {"maxiter": 100}}


def test__project_keywords_invalid_template() -> None:
    """Test that an invalid template type raises TypeError."""
    with pytest.raises(TypeError, match="must be a dictionary"):
        project_keywords({}, ["not", "a", "dict"])


def test__default_attributes(calc: Calculation) -> None:
    """Test the default attributes of a Calculation."""
    assert calc.super_program is None
    assert calc.cmdline_args == []


def test__project_filters_top_level_fields(calc: Calculation) -> None:
    """Test that projection of a template filters top-level fields."""
    template = {"program": None, "method": None}
    projected = project(calc, template)
    assert set(projected.keys()) == {"program", "method"}
    assert "calc_type" not in projected


def test__project_filters_nested_keywords(calc: Calculation) -> None:
    """Test that projection of a template filters nested keywords."""
    template = {"program_keywords": {"dft_functional": None}}
    projected = project(calc, template)
    assert projected["program_keywords"] == {"dft_functional": "b3lyp"}
    assert "scf_type" not in projected["program_keywords"]


def test__project_immutability(calc: Calculation) -> None:
    """Ensure project does not mutate the original object."""
    template = {"program": "only"}
    project(calc, template)
    assert "method" in calc.model_dump()


def test__registry_registration(calc: Calculation) -> None:
    """Test the registration of a user-defined registry."""
    reg = HashRegistry()

    @reg.register("test")
    def sample(calc: Calculation) -> str:  # noqa: ARG001
        return "abc"

    assert "test" in reg.available()
    assert reg.get("test")(calc) == "abc"


def test__registry_duplicate_error() -> None:
    """Test that registering duplicate registries raises a ValueError."""
    reg = HashRegistry()
    reg.register("test")(lambda t: "a")  # noqa: ARG005
    with pytest.raises(ValueError, match="already registered"):
        reg.register("test")(lambda t: "b")  # noqa: ARG005


def test__hash_minimal_ignores_keywords() -> None:
    """Test that hash_minimal() ignores keywords."""
    calc1 = Calculation(
        program="orca", method="hf", program_keywords={"a": 1}, calc_type="e"
    )
    calc2 = Calculation(
        program="orca", method="hf", program_keywords={"b": 2}, calc_type="e"
    )
    # Minimal hash looks at program, method, basis
    assert hash_minimal(calc1) == hash_minimal(calc2)


def test__hash_full_detects_keyword_changes() -> None:
    """Test that hash_full() does not ignore keywords."""
    calc1 = Calculation(
        program="orca", method="hf", program_keywords={"a": 1}, calc_type="e"
    )
    calc2 = Calculation(
        program="orca", method="hf", program_keywords={"a": 2}, calc_type="e"
    )
    assert hash_full(calc1) != hash_full(calc2)


def test__calculation_hash_routing(calc: Calculation) -> None:
    """Tests the calculation_hash() wrapper."""
    hash1 = calculation_hash(calc, name="minimal")
    hash2 = hash_minimal(calc)
    assert hash1 == hash2
