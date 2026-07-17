# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

autostorage is a SQLModel/SQLAlchemy persistence layer for computational chemistry workflow
data, built on top of `automol`. It stores molecular geometries, identities, trajectories,
stationary points, calculation results, and the calculations/steps that connect them, as a
graph of related database rows.

## Commands

All tasks run through Pixi (`pixi run <task>`), defined in `pixi.toml` under `[feature.dev.tasks]`:

- `pixi run fmt` — format with Ruff
- `pixi run lint` — lint with Ruff (`--fix`)
- `pixi run types` — static type-check with `ty`
- `pixi run imports` — enforce module layering with `lint-imports` (import-linter)
- `pixi run test` — run the full pytest suite
- `pixi run pre-commit` — run all of the above via lefthook, in order (fmt → lint → types → imports → test), then check the tree is clean
- `pixi run cov-view` — open the HTML coverage report

Single test: invoke `pytest` directly inside the pixi env, e.g.
`pixi run -e dev pytest tests/test_models.py::test_name`.

Note: pytest is configured with `--doctest-modules`, so doctests in `src/` docstrings are
collected and run as part of the suite. Coverage must stay ≥80% (`fail_under = 80` in
`pyproject.toml`), with branch coverage enabled.

## Architecture

### Module layering (enforced by import-linter)

`pyproject.toml` defines a strict layer contract ("Autostorage Layering") — higher layers may
depend on lower ones, never the reverse:

```
autostorage.utils               (highest)
autostorage.database
autostorage.events
autostorage.models
autostorage.types | autostorage.exc   (lowest)
```

Adding an import that violates this order will fail `pixi run imports`. Unlike `automol`,
`autostorage` is a flat module structure (no sub-packages).

### Relationship to automol

Row models extend automol's core data models directly rather than wrapping them: `GeometryRow`
extends `automol.Geometry`, `IdentityRow` extends `automol.Identity`. Any conversion to/from
other external formats is delegated to automol's own conversion functions rather than
reimplemented here.

### Current module map

- `models.py` — SQLModel row definitions: `GeometryRow`, `IdentityRow`, `TrajectoryRow`,
  `StationaryPointRow`, result rows (`EnergyRow`, `GradientRow`, `HessianRow`, all extending
  `BaseResultRow`), `StageRow`, `StepRow` (a step between two stages, with a barrierless flag),
  `ModelRow`, `CalculationRow`, `ValidationRow`, `IdentityExtraRow`, and link tables
  (`CalculationGeometryLink`, `CalculationTrajectoryLink`, `TrajectoryGeometryLink`,
  `StationaryIdentityLink`, `StationaryStageLink`, `StepValidationLink`). Base classes:
  `BaseRow`, `BaseResultRow`, `BaseLink`.
- `events.py` — SQLAlchemy ORM event listeners: shape validation for `GradientRow`/`HessianRow`,
  `validate_geometry_orders`, `add_inchi_identities` (auto-attaches InChI/SMILES `IdentityRow`s
  to new `StationaryPointRow`s via `automol.Algorithm` on flush), and stage-order/barrierless
  checks for `StepRow`.
- `database.py` — `Database`: SQLite engine/session manager (`add`, `merge`, `flush`, `commit`,
  `delete`, `get`, `exec_first`/`one`/`all`, `close`, WAL-mode support).
- `types.py` — `CalcType` (StrEnum: OPT, OPT_TS, CONFORMER, SCAN, IRC, MEP, ENERGY, GRADIENT,
  FREQUENCY, THERMO, UNDEFINED), `Role` (INPUT/OUTPUT), and SQLAlchemy `TypeDecorator`s
  (`FloatArrayTypeDecorator`, `PathTypeDecorator`, `Float32BytesTypeDecorator`) for storing
  NumPy arrays/paths in SQLite.
- `exc.py` — `ResultShapeError`, `MissingPrimaryKeyError`.

### Docstrings

NumPy docstring convention (`tool.ruff.lint.pydocstyle` = `"numpy"`), and doctest examples in
docstrings are executed as tests — keep them runnable and accurate.

### Notes

Minimize verbosity when performing work to reduce unnecessary token costs.