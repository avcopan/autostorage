"""Model hash module tests."""

from collections.abc import Generator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from autostorage import Model
from autostorage.model_hash import (
    ModelHashAlgorithm,
    ModelHashAlgorithmRegistry,
    ModelHashKind,
    exact_hash,
    minimal_hash,
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


class TestMinimalHash:
    """Tests for minimal@1."""

    @pytest.mark.parametrize(
        ("program", "method", "basis", "keywords", "expected"),
        [
            ("ORCA", "B3LYP", "6-31G*", {"TightSCF": True}, "b3lyp/6-31g*"),
            ("orca", " b3lyp", "6-31g*", {}, "b3lyp/6-31g*"),
            ("psi4", "HF", None, None, "hf"),
            ("psi4", "HF", "  ", None, "hf"),
            ("psi4", "HF", "", None, "hf"),
        ],
    )
    def test_value(
        self,
        program: str,
        method: str,
        basis: str | None,
        keywords: dict[str, Any] | None,
        expected: str,
    ) -> None:
        """The value is the stripped, lower-cased method and basis."""
        assert minimal_hash.hash_fn(program, method, basis, keywords) == expected

    def test_registered(self) -> None:
        """It is registered as minimal@1."""
        assert ModelHashAlgorithmRegistry.get("minimal@1") is minimal_hash
        assert minimal_hash.kind == ModelHashKind.MINIMAL
        assert minimal_hash.programs is None

    def test_hash_model(self) -> None:
        """`hash` accepts an in-memory model."""
        model = Model(program="orca", method="B3LYP", basis="6-31G*")
        assert minimal_hash.hash(model) == "b3lyp/6-31g*"


class TestExactHash:
    """Tests for exact@1."""

    @staticmethod
    def _hash(
        program: str = "orca",
        method: str = "b3lyp",
        basis: str | None = "6-31g*",
        keywords: dict[str, Any] | None = None,
    ) -> str:
        return exact_hash.hash_fn(program, method, basis, keywords)

    def test_registered(self) -> None:
        """It is registered as exact@1."""
        assert ModelHashAlgorithmRegistry.get("exact@1") is exact_hash
        assert exact_hash.kind == ModelHashKind.EXACT

    def test_is_sha256_hex(self) -> None:
        """The value is a 64-character hex digest."""
        value = self._hash()
        assert len(value) == 64
        int(value, 16)

    def test_keyword_order_irrelevant(self) -> None:
        """Dicts with the same items in a different order hash equally, nested too."""
        a = {"a": 1, "b": {"x": 1, "y": 2}}
        b = {"b": {"y": 2, "x": 1}, "a": 1}
        assert self._hash(keywords=a) == self._hash(keywords=b)

    def test_case_sensitive(self) -> None:
        """Keyword names, and programs, are not case-folded."""
        assert self._hash(keywords={"TightSCF": True}) != self._hash(
            keywords={"tightscf": True}
        )
        assert self._hash(program="orca") != self._hash(program="psi4")

    def test_none_keywords_equal_empty(self) -> None:
        """`None` keywords count as `{}`."""
        assert self._hash(keywords=None) == self._hash(keywords={})

    def test_program_version_ignored(self) -> None:
        """Models that differ only in `program_version` hash equally."""
        a = Model(program="orca", program_version="5.0", method="b3lyp")
        b = Model(program="orca", program_version="6.1", method="b3lyp")
        assert exact_hash.hash(a) == exact_hash.hash(b)

    def test_keywords_matter(self) -> None:
        """Different keywords give different hashes."""
        assert self._hash(keywords={"a": 1}) != self._hash(keywords={"a": 2})

    def test_unserializable_keywords(self) -> None:
        """Non-JSON keyword values raise `TypeError`."""
        with pytest.raises(TypeError):
            self._hash(keywords={"x": object()})
