"""Calculation hash registry."""

from collections.abc import Callable

from .core import Calculation, projected_hash
from .util import hash_from_dict

HashFunc = Callable[[Calculation], str]


class HashRegistry:
    """Hash registry."""

    def __init__(self) -> None:
        """Initialize hash registry."""
        self._registry: dict[str, HashFunc] = {}

    def register(self, name: str) -> Callable[[HashFunc], HashFunc]:
        """Register function in hash registry (decorator)."""

        def decorator(func: HashFunc) -> HashFunc:
            if name in self._registry:
                msg = f"Hash '{name}' is already registered"
                raise ValueError(msg)
            self._registry[name] = func
            return func

        return decorator

    def get(self, name: str) -> HashFunc:
        """Get registered hash by name."""
        try:
            return self._registry[name]
        except KeyError as err:
            msg = f"Unknown hash type '{name}'. Available: {sorted(self._registry)}"
            raise KeyError(msg) from err

    def available(self) -> tuple[str, ...]:
        """Get registered hash names."""
        return tuple(self._registry)


hash_registry = HashRegistry()


@hash_registry.register("full")
def hash_full(calc: Calculation) -> str:
    """
    Generate maximal hash for calculation.

    Parameters
    ----------
    calc
        Calculation metadata.

    Returns
    -------
        Hash string.
    """
    input_fields = {
        "program",
        "method",
        "basis",
        "keywords",
        "cmdline_args",
        "files",
        "calctype",
        "program_version",
    }
    calc_dct = calc.model_dump(include=input_fields)
    return hash_from_dict(calc_dct)


@hash_registry.register("minimal")
def hash_minimal(calc: Calculation) -> str:
    """
    Generate minimal hash for calculation.

    Parameters
    ----------
    calc
        Calculation metadata.

    Returns
    -------
        Hash string.
    """
    template = {
        "program": "PROGRAM",
        "method": "METHOD",
        "basis": "BASIS",
    }
    return projected_hash(calc, template)  # ty:ignore[invalid-argument-type]


def calculation_hash(calc: Calculation, name: str = "minimal") -> str:
    """
    Hash calculation metadata using named hash from registry.

    Parameters
    ----------
    calc
        Calculation metadata.
    name
        Hash registry name, e.g. "full" or "minimal". Use
        `hash_registry.available()` to get list of available names.

    Returns
    -------
        Hash string.
    """
    func = hash_registry.get(name)
    return func(calc)
