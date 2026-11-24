"""Pytest configuration and shared fixtures."""

import itertools
from collections.abc import Callable

import pytest

from autostorage.models import (
    CalculationRow,
    GeometryRow,
    ModelRow,
    StageRow,
    StationaryPointRow,
)

# Local, git-ignored scratch scripts (see .gitignore) are not tests, but
# `--doctest-modules` would otherwise import (and run) them.
collect_ignore_glob = ["scratch*"]


@pytest.fixture
def make_point() -> Callable[..., StationaryPointRow]:
    """Create factory for unsaved stationary points sharing one calculation.

    Each point gets its own geometry (H2 by default), translated further along x
    on each call so that the stored geometries are distinct.
    """
    calculation = CalculationRow(
        model=ModelRow(program="psi4", method="B3LYP"), calc_type="opt"
    )
    shifts = itertools.count()

    def _make(
        symbols: list[str] | None = None,
        *,
        charge: int = 0,
        spin: int = 0,
        order: int = 0,
    ) -> StationaryPointRow:
        symbols = symbols or ["H", "H"]
        shift = 0.01 * next(shifts)
        coords = [[shift, 0.0, 0.74 * i] for i in range(len(symbols))]
        geo = GeometryRow(symbols=symbols, coordinates=coords, charge=charge, spin=spin)
        return StationaryPointRow(geometry=geo, calculation=calculation, order=order)

    return _make


@pytest.fixture
def make_stage(
    make_point: Callable[..., StationaryPointRow],
) -> Callable[..., StageRow]:
    """Create factory for unsaved stages holding one new H2 point each."""

    def _make(*, is_ts: bool = False) -> StageRow:
        return StageRow.from_points([make_point(order=int(is_ts))], is_ts=is_ts)

    return _make
