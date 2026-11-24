# CLAUDE.md

autostorage is a SQLModel/SQLAlchemy persistence layer for computational chemistry workflow data, built on autogeom.
Read `CONTRIBUTING.md` for the workflow, the design rules (the `Row` suffix, conversions and validation from autogeom, the import layers), and the docstring conventions.
The user guide is in `user_guide/`, and `.claude/skills/` comes from the copier template.
`.claude/skills/sqlmodel` and `.agents/skills/sqlmodel` link to the official SQLModel skill inside the installed package, so run `pixi install` first; after a Python upgrade, repair them with `pixi run uvx library-skills --yes --claude`.

## Commands

- Run everything through Pixi (`pixi run <task>`, or `pixi run -e test python ...`).
  autogeom and the other dependencies are only installed in the Pixi environments, not in the system Python.
- `pixi run pre-commit` runs all checks. A single test: `pixi run -e test pytest tests/test_models.py::TestGeometryRow::test_name`.
- Tests are grouped into `Test*` classes by the row or function under test.

## Behavior that isn't obvious from the models

`events.py` binds SQLAlchemy ORM event listeners to `AutostorageSession`, the session type that `Database.session()` returns:
- `GeometryRow.hash` is set to `geometry_hash()` (SHA-256 of symbols, coordinates, charge, spin) on insert and update; its unique index rejects storing an equal geometry twice with an `IntegrityError`.
- Opening a `Database` seeds `IdentityAlgorithmRow`, `ModelHashAlgorithmRow` and `PropertyKindRow` from their in-memory registries.
- Before a flush, property values are shape-checked and cast to their kind's dtype, and a stationary point marked valid must have a Hessian.
- A non-pseudo stationary point's `is_validated` is set on flush to whether every Hessian of its geometry has `order` negative eigenvalues (`autogeom.stationary_point_order`). A mismatch resets it with a `StationaryOrderWarning`. It is rechecked when the point or a Hessian of its geometry is added, changed, or deleted.
- New stationary points get an `IdentityRow` for every algorithm in `IdentityAlgorithmRegistry` (`identity.py`; regenerated when the geometry or `order` changes). Failing algorithms are skipped with an `IdentityGenerationWarning`, and ones restricted by `orders` (InChIs and SMILES) are skipped when `algorithm.applies_to(order)` is `False`.
- New `ModelRow`s get a `ModelHashRow` for every algorithm in `ModelHashAlgorithmRegistry` (`model_hash.py`) that `applies_to(program)`, and are rehashed when `program`, `method`, `basis` or `keywords` change (reassign `keywords` after a nested edit). Failing, empty or too-long (255+ characters) hashes are skipped with a `ModelHashGenerationWarning`. There is no backfill.
- A stage is a multiset: `StageStationaryLink.count` says how many times its point occurs (A + A is one link, count 2). A new or changed stage must have a point, and a TS stage exactly one, with count 1. `StageRow.stationaries` and `StationaryPointRow.stages` are read-only; write `stationary_links`, or use `StageRow.from_points`. Deleting a point deletes its links but keeps its stages, even if they become empty.
- `StageRow.hash` is set to `stage_hash()` (SHA-256 of `is_ts` and the sorted (point ID, count) pairs) on flush, for new stages and stages whose links or `is_ts` changed; its unique index rejects storing the same stage twice. Share stages with `StageRow.get_or_create`, which finds a pending or stored match. A stage that loses a point because the point was deleted keeps its old hash.
- `StepRow` stage IDs are sorted (`stage_id1 < stage_id2`), and `is_barrierless` must match whether there is a transition-state stage.
- A step must be balanced: its stages (TS stage included) have the same element counts and total charge, summed over points times counts. Spin is not checked (steps may be spin-forbidden). It is checked for new or changed steps and the steps of changed stages.
- A trajectory's `ndim` is inferred from its geometry indices if unset.
- Trajectory axes (`TrajectoryAxisRow`) are validated, and missing `GeometryTrajectoryLink.values` of distance/angle/dihedral axes are measured with autogeom (quantities are converted to the axis's units).

Nothing commits automatically: call `session.commit()`.
Arrays are stored zlib-compressed by `CompressedArrayTypeDecorator` (float64, but float32 for Hessians), and `IdentityStationaryLink.identity_cache` as zlib-compressed JSON by `CompressedJSONTypeDecorator`.
Deleting a row deletes its link rows and the data that needs it (a model's calculations and hash links; a geometry's or calculation's properties and stationary points; a point's identity and stage links; a stage's links; a calculation's validations), but not geometries, stages, steps, identities, or model hashes.
Identities and stages are reached through link rows (`StationaryPointRow.identity_links`, `IdentityRow.stationary_links`; `StationaryPointRow.stage_links`, `StageRow.stationary_links`); removing a link from either list deletes it.

## Style

Keep docstrings and comments short: one-line summaries where possible, without restating what a name or type hint already says.
