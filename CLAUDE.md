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
- Opening a `Database` seeds `IdentityAlgorithmRow` and `PropertyKindRow` from their in-memory registries.
- Before a flush, property values are shape-checked and cast to their kind's dtype, and a stationary point marked valid must have a Hessian.
- New stationary points get an `IdentityRow` for every algorithm in `IdentityAlgorithmRegistry` (`identity.py`; regenerated when the geometry or `order` changes). Failing algorithms are skipped with an `IdentityGenerationWarning`, and `minima_only` ones (InChIs and SMILES) are skipped when `order != 0`.
- `StepRow` stage IDs are sorted (`stage_id1 < stage_id2`), and `is_barrierless` must match whether there is a transition-state stage.
- A trajectory's `ndim` is inferred from its geometry indices if unset.
- Trajectory axes (`TrajectoryAxisRow`) are validated, and missing `GeometryTrajectoryLink.values` of distance/angle/dihedral axes are measured with autogeom (quantities are converted to the axis's units).

Nothing commits automatically: call `session.commit()`.
Arrays are stored zlib-compressed by `CompressedArrayTypeDecorator` (float64, but float32 for Hessians), and `IdentityStationaryLink.identity_cache` as zlib-compressed JSON by `CompressedJSONTypeDecorator`.
Deleting a row deletes its link rows and the data that needs it (a model's calculations; a geometry's or calculation's properties and stationary points; a calculation's validations), but not geometries, stages, steps, or identities.
Identities are reached through link rows (`StationaryPointRow.identity_links`, `IdentityRow.stationary_links`); removing a link from either list deletes it.

## Style

Keep docstrings and comments short: one-line summaries where possible, without restating what a name or type hint already says.
