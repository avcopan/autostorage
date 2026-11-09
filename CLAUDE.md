# CLAUDE.md

autostorage is a SQLModel/SQLAlchemy persistence layer for computational chemistry workflow data, built on automol.
Read `CONTRIBUTING.md` for the workflow, the design rules (the `Row` suffix, conversions and validation from automol, the import layers), and the docstring conventions.
The user guide is in `user_guide/`, and `.claude/skills/` comes from the copier template.
`.claude/skills/sqlmodel` and `.agents/skills/sqlmodel` link to the official SQLModel skill inside the installed package, so run `pixi install` first; after a Python upgrade, repair them with `pixi run uvx library-skills --yes --claude`.

## Commands

- Run everything through Pixi (`pixi run <task>`, or `pixi run -e test python ...`).
  automol and the other dependencies are only installed in the Pixi environments, not in the system Python.
- `pixi run pre-commit` runs all checks. A single test: `pixi run -e test pytest tests/test_models.py::TestGeometryRow::test_name`.
- Tests are grouped into `Test*` classes by the row or function under test.

## Behavior that isn't obvious from the models

`events.py` binds SQLAlchemy ORM event listeners to `AutostorageSession`, the session type that `Database.session()` returns:
- Opening a `Database` seeds `IdentityAlgorithmRow` and `PropertyKindRow` from their in-memory registries.
- Before a flush, property values are shape-checked and cast to their kind's dtype, and a stationary point marked valid must have a Hessian.
- New stationary points get an `IdentityRow` for every registered automol algorithm (regenerated when the geometry changes). Failing algorithms are skipped with an `IdentityGenerationWarning`.
- `StepRow` stage IDs are sorted (`stage_id1 < stage_id2`), and `is_barrierless` must match whether there is a transition-state stage.
- A trajectory's `ndim` is inferred from its geometry indices if unset.

Nothing commits automatically: call `session.commit()`.
Arrays are stored zlib-compressed by `CompressedArrayTypeDecorator` (float64, but float32 for Hessians).

## Style

Keep docstrings and comments short: one-line summaries where possible, without restating what a name or type hint already says.
