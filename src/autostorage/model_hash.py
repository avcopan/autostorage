"""Model hash algorithm registry with default definitions."""

import hashlib
import json
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
    "exact_hash",
    "minimal_hash",
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
        Hash values must be under 255 characters (longer ones are skipped with a
        warning); a function that would return a longer value should hash it
        itself.

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


def minimal_hash_fn(
    program: str,  # noqa: ARG001
    method: str,
    basis: str | None,
    keywords: Mapping[str, Any] | None,  # noqa: ARG001
) -> str:
    """Method and basis, stripped and lower-cased: ``"b3lyp/6-31g*"``."""
    method = method.strip().lower()
    basis = (basis or "").strip().lower()
    return f"{method}/{basis}" if basis else method


minimal_hash = ModelHashAlgorithmRegistry.register(
    name="minimal@1", kind=ModelHashKind.MINIMAL, hash_fn=minimal_hash_fn
)
"""Method and basis, lower-cased (kind: minimal)."""


def exact_hash_fn(
    program: str,
    method: str,
    basis: str | None,
    keywords: Mapping[str, Any] | None,
) -> str:
    """SHA-256 of the canonical JSON of program, method, basis and keywords.

    Raises:
        TypeError: If the keywords aren't JSON-serializable.
    """
    payload = {
        "program": program,
        "method": method,
        "basis": basis,
        "keywords": keywords or {},
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


exact_hash = ModelHashAlgorithmRegistry.register(
    name="exact@1", kind=ModelHashKind.EXACT, hash_fn=exact_hash_fn
)
"""Program, method, basis and keywords, exactly as given (kind: exact)."""
