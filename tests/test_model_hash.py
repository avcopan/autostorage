"""Model hash module tests."""

from collections.abc import Generator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from autostorage.model_hash import (
    ModelHashAlgorithm,
    ModelHashAlgorithmRegistry,
    ModelHashKind,
)


def _constant_hash(
    program: str,  # noqa: ARG001
    method: str,  # noqa: ARG001
    basis: str | None,  # noqa: ARG001
    keywords: Any,  # noqa: ANN401, ARG001
) -> str:
    """Hash function returning a constant."""
    return "x"


@pytest.fixture
def registered() -> Generator[list[ModelHashAlgorithm]]:
    """Collect test algorithms and remove them from the registry afterwards."""
    algorithms: list[ModelHashAlgorithm] = []
    yield algorithms
    for algorithm in algorithms:
        ModelHashAlgorithmRegistry.algorithms.remove(algorithm)


class TestModelHashAlgorithm:
    """Tests for ModelHashAlgorithm."""

    def test_frozen(self) -> None:
        """Attributes can't be reassigned."""
        algorithm = ModelHashAlgorithm("t@1", ModelHashKind.MINIMAL, _constant_hash)
        with pytest.raises(FrozenInstanceError):
            algorithm.name = "other"  # ty: ignore[invalid-assignment]

    def test_applies_to_case_insensitive(self) -> None:
        """Programs are matched case-insensitively."""
        algorithm = ModelHashAlgorithm(
            "t@1", ModelHashKind.FINE, _constant_hash, programs=frozenset({"orca"})
        )
        assert algorithm.applies_to("ORCA")
        assert not algorithm.applies_to("psi4")

    def test_applies_to_any_program(self) -> None:
        """`programs=None` applies to every program."""
        algorithm = ModelHashAlgorithm("t@1", ModelHashKind.MINIMAL, _constant_hash)
        assert algorithm.applies_to("anything")


class TestModelHashAlgorithmRegistry:
    """Tests for ModelHashAlgorithmRegistry."""

    def test_register_and_get(self, registered: list[ModelHashAlgorithm]) -> None:
        """A registered algorithm is returned by name."""
        algorithm = ModelHashAlgorithmRegistry.register(
            "reg_test@1", ModelHashKind.MINIMAL, _constant_hash
        )
        registered.append(algorithm)
        assert ModelHashAlgorithmRegistry.get("reg_test@1") is algorithm

    def test_register_duplicate(self, registered: list[ModelHashAlgorithm]) -> None:
        """Registering a name twice raises."""
        registered.append(
            ModelHashAlgorithmRegistry.register(
                "dup_test@1", ModelHashKind.MINIMAL, _constant_hash
            )
        )
        with pytest.raises(ValueError, match="already registered"):
            ModelHashAlgorithmRegistry.register(
                "dup_test@1", ModelHashKind.MINIMAL, _constant_hash
            )

    def test_get_unknown(self) -> None:
        """An unknown name raises a KeyError that lists the available names."""
        with pytest.raises(KeyError, match="Available"):
            ModelHashAlgorithmRegistry.get("nope")

    def test_register_lowercases_programs(
        self, registered: list[ModelHashAlgorithm]
    ) -> None:
        """Programs are stored lower-case."""
        algorithm = ModelHashAlgorithmRegistry.register(
            "case_test@1", ModelHashKind.FINE, _constant_hash, programs=["ORCA", "Psi4"]
        )
        registered.append(algorithm)
        assert algorithm.programs == frozenset({"orca", "psi4"})
