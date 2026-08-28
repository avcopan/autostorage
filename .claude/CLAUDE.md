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
- `pixi run local` — toggle `pixi.toml`'s `automol` dependency between the pinned release and a
  local `../automol` checkout, via the `# local:true`/`# local:false` comment markers already in
  the file (see "Relationship to automol" below)
- `pixi run local-pre-commit` — a second lefthook target, distinct from `pre-commit`
- `pixi run docs-build` / `pixi run docs-view` — build/view the Sphinx docs (`feature.docs` env)

Single test: invoke `pytest` directly inside the pixi env, e.g.
`pixi run -e dev pytest tests/test_models.py::TestGeometryRow::test_name` (tests are organized
into `Test*` classes grouped by row/function under test).

Note: pytest is configured with `--doctest-modules`, so doctests in `src/` docstrings are
collected and run as part of the suite. Coverage must stay ≥80% (`fail_under = 80` in
`pyproject.toml`), with branch coverage enabled.

Don't invoke bare `python`/`python3` — `automol` and other deps aren't on the system interpreter,
only inside the pixi env. Always go through `pixi run` (e.g. `pixi run -e dev pytest ...`).

## Architecture

### Module layering (enforced by import-linter)

`pyproject.toml` defines a strict layer contract ("Autostorage Layering") — higher layers may
depend on lower ones, never the reverse:

```
autostorage.database            (highest)
autostorage.events
autostorage.models
autostorage.types                (lowest)
```

Adding an import that violates this order will fail `pixi run imports`. `autostorage` is a flat
module structure — all modules live directly in `src/autostorage/`.

### Relationship to automol

Row models extend automol's core data models directly rather than wrapping them: `GeometryRow`
extends `automol.Geometry`, `IdentityRow` extends `automol.Identity`. Any conversion to/from
other external formats is delegated to automol's own conversion functions rather than
reimplemented here.

### Current module map

- `models.py` — SQLModel row definitions, organized in sections:
  - Link tables (named alphabetically by the entities they connect): `CalculationGeometryLink`,
    `CalculationTrajectoryLink`, `GeometryTrajectoryLink`, `IdentityStationaryLink`,
    `StageStationaryLink`, `StepValidationLink`
  - Existential data rows: `GeometryRow` (extends `automol.Geometry`), `TrajectoryRow`,
    `ModelRow`, `CalculationRow`, result rows (`EnergyRow`, `GradientRow`, `HessianRow`),
    `ValidationRow`
  - Stationary point rows: `StationaryPointRow`
  - Reaction network rows: `StageRow`, `StepRow` (a step between two stages, with a barrierless
    flag)
  - Identity rows: `IdentityRow` (extends `automol.Identity`), `IdentityExtraRow`

- `events.py` — SQLAlchemy ORM event listeners, by concern:
  - Shape validation: `verify_gradient_shapes_before_flush`, `verify_hessian_shapes_before_flush`
  - Trajectory validation: `verify_trajectory_geometry_ndim_insert` (ensures geometry index
    length matches trajectory ndim)
  - Auto-managed identities: `add_inchi_identities_before_flush` (attaches an InChI `IdentityRow`
    to newly inserted stationary points), `add_smiles_extras_before_flush` /
    `add_hill_extras_before_flush` (attach SMILES / Hill formula as `IdentityExtraRow`s once an
    InChI identity is present). Private `_find_or_create_identity`/`_find_or_create_identity_extra`
    helpers dedup these against existing rows and pending session inserts.
  - Step validation: `sort_step_stage_ids` (auto-sorts stage_id1 < stage_id2),
    `verify_step_barrierless_consistency` (verifies is_barrierless matches stage_id_ts state)

- `database.py` — `Database`: SQLite engine/session manager. `__init__` creates the engine
  (with `PRAGMA foreign_keys=ON` and a sort-keys JSON serializer) and the schema via
  `SQLModel.metadata.create_all`; `session()` returns a fresh `Session` bound to that engine
  (use as a context manager; nothing auto-commits); `close()` disposes the engine.

- `types.py` — Type definitions and utilities:
  - `Role` (StrEnum: INPUT/OUTPUT) — relationship between calculations and geometries/trajectories
  - `CompressedArrayTypeDecorator` — SQLAlchemy `TypeDecorator` storing NumPy arrays as
    zlib-compressed binary data in SQLite
  - `_fk_field()` — helper for building foreign-key fields with ON DELETE CASCADE

### Docstrings

NumPy docstring convention (`tool.ruff.lint.pydocstyle` = `"numpy"`), and doctest examples in
docstrings are executed as tests — keep them runnable and accurate.

### Notes

- Minimize chat/response verbosity when performing work to reduce unnecessary token costs.
- Keep docstrings and comments minimal: one-line NumPy-style summaries where the convention
  allows, no restating what a name/type hint already conveys. Reserve comments for genuinely
  non-obvious invariants — most docstrings in this repo don't need that much.