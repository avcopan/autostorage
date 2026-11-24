"""Model hash algorithm registry with default definitions."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

from .domain import Model
from .types import ModelHashKind

__all__ = [
    "ModelHashAlgorithm",
    "ModelHashAlgorithmRegistry",
    "ModelHashKind",
    "ModelHashProtocol",
]


@runtime_checkable
class ModelHashProtocol(Protocol):
    """Protocol for model hash functions."""

    def __call__(
        self,
        program: str,
        method: str,
        basis: str | None,
        keywords: Mapping[str, Any] | None,
    ) -> str:
        """Generate the hash of a model's electronic-structure specification."""
        ...


@dataclass(frozen=True)
class ModelHashAlgorithm:
    """A registered model hash algorithm.

    Unlike an identity algorithm, it has no parent: a model's hash depends on
    that model alone, so there is no pool of other models to narrow down.

    Attributes:
        name: Unique algorithm name (mirrored into `ModelHashAlgorithmRow`).
        kind: How fine-grained the hash is.
        hash_fn: ``(program, method, basis, keywords) -> str``.
        programs: Programs the algorithm applies to (lower-case). `None` if it
            applies to any program.
    """

    name: str
    kind: ModelHashKind
    hash_fn: ModelHashProtocol
    programs: frozenset[str] | None = None

    def applies_to(self, program: str) -> bool:
        """Check whether the algorithm applies to a program (case-insensitive)."""
        return self.programs is None or program.lower() in self.programs

    def hash(self, model: Model) -> str:
        """Hash an in-memory model, e.g. to look it up before running it."""
        return self.hash_fn(model.program, model.method, model.basis, model.keywords)


class ModelHashAlgorithmRegistry:
    """Central registry of all known model hash algorithms."""

    algorithms: ClassVar[list[ModelHashAlgorithm]] = []

    @classmethod
    def register(
        cls,
        name: str,
        kind: ModelHashKind,
        hash_fn: ModelHashProtocol,
        *,
        programs: Iterable[str] | None = None,
    ) -> ModelHashAlgorithm:
        """Create and register a model hash algorithm.

        Register algorithms before opening a `Database`, which mirrors them into
        its `model_hash_algorithm` table. The foreign key to that table is
        enforced, so a model hashed by an unseeded algorithm fails on flush.
        Hash values must be under 255 characters; a function that would return
        a longer value should hash it itself.

        Args:
            name: Unique algorithm name.
            kind: How fine-grained the hash is.
            hash_fn: Function hashing a model's electronic-structure specification.
            programs: Programs the algorithm applies to (stored lower-case).
                `None` if it applies to any program.

        Raises:
            ValueError: If an algorithm named `name` is already registered.
        """
        if any(name == a.name for a in cls.algorithms):
            msg = f"Model hash algorithm {name!r} is already registered."
            raise ValueError(msg)
        programs = None if programs is None else frozenset(p.lower() for p in programs)
        algorithm = ModelHashAlgorithm(
            name=name, kind=kind, hash_fn=hash_fn, programs=programs
        )
        cls.algorithms.append(algorithm)
        return algorithm

    @classmethod
    def get(cls, name: str) -> ModelHashAlgorithm:
        """Get a registered model hash algorithm by name.

        Raises:
            KeyError: If no algorithm named `name` is registered.
        """
        try:
            return next(a for a in cls.algorithms if a.name == name)
        except StopIteration:
            available = ", ".join(sorted(a.name for a in cls.algorithms))
            msg = f"Unknown model hash algorithm {name!r}. Available: {available}"
            raise KeyError(msg) from None
