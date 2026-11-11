# Copilot instructions for autostorage

autostorage is a Python (≥3.12) persistence layer for computational chemistry workflow data, built on [SQLModel](https://sqlmodel.tiangolo.com/)/SQLAlchemy and [`autogeom`](https://github.com/avcopan/autogeom). It stores geometries, trajectories, calculations, property values (energies, gradients, Hessians), stationary points, chemical identities, and reaction stages/steps as a graph of related rows in a SQLite database. `GeometryRow` extends `autogeom.Geometry` directly, so autogeom's validation (symbols, atom count, spin parity, `pint` coordinates) applies to stored geometries. The environment and all tooling are managed by [Pixi](https://pixi.sh). Run everything through `pixi run <task>` or `pixi run -e dev <cmd>`, and never call a bare `python`/`pip`.

## Package modules (`src/autostorage/`)

The layers are strict and enforced by import-linter. A module may import from lower layers only: `database` → `events` → `query` → `property` | `identity` → `models` → `types`.

- **`database.py`**: `Database(path, *, echo=False)`, the SQLite engine/session manager (also a context manager). `__init__` builds the engine with `URL.create`, enables `PRAGMA foreign_keys=ON`, serializes JSON with sorted keys, creates the schema, and seeds the registry tables (`create_identity_algorithms`, `create_property_kinds`). `session()` returns a fresh `AutostorageSession`; nothing auto-commits. `close()` disposes the engine.
- **`events.py`**: `AutostorageSession` (a `sqlmodel.Session` subclass) and the ORM event listeners, in sections:
  - Registry seeding: `create_identity_algorithms` (mirrors `IdentityAlgorithmRegistry` into `IdentityAlgorithmRow`, parents first, by name) and `create_property_kinds` (mirrors `PropertyKindRegistry` into `PropertyKindRow`, by name).
  - Step checks (mapper-level): `sort_step_stage_ids` and `verify_step_barrierless_consistency`.
  - Session-level `before_flush` checks: `verify_property_values_before_flush` (shape check and dtype cast), `verify_valid_stationary_has_hessian`, and `verify_trajectory_geometry_ndim` (infers and persists `TrajectoryRow.ndim`).
  - Automatic identities: `add_registry_identities_before_flush` attaches an `IdentityRow` for every registered algorithm to new stationary points, and regenerates them when a stationary point's geometry is reassigned. Child algorithms (e.g. SMILES, parent InChI) get `other_geos` from persisted and same-flush siblings. Failing algorithms issue an `IdentityGenerationWarning` and are skipped.
- **`query.py`**: select-statement factories, run with `session.exec(...)`. `stationary_point_by_identity(algorithm, value, *, include_pseudo=False)` accepts an `IdentityAlgorithm` (e.g. `autostorage.rdkit_inchi`), an `IdentityAlgorithmRow`, or a name.
- **`identity.py`**: `IdentityAlgorithm` (frozen Pydantic model: `name`, `kind`, `identity_fn`, `parent`), `IdentityAlgorithmRegistry.register(...)`/`.get(name)`, `IdentityProtocol`, and the built-in `rdkit_inchi`, `rdkit_smiles` (parent `rdkit_inchi`), and `hill_formula`, which call `autogeom.inchi`, `autogeom.smiles`, and `autogeom.formula`. `IdentityKind` is defined in `types.py`.
- **`property.py`**: `PropertyKind` (frozen Pydantic model: `name`, `validation_fn`, `dtype`), `PropertyKindRegistry.register(...)`/`.get(name)`, `PropertyValidationProtocol`, and the built-in `energy_property_kind`, `gradient_property_kind`, and `hessian_property_kind` (float32).
- **`models.py`**: SQLModel table rows, in sections. Private column helpers come first: `_fk_field()`/`_link_fk_field()` (`ON DELETE CASCADE` foreign keys), `_role_column()`, and `_json_dict_column()` (`MutableDict` JSON, so in-place dict edits persist).
  - Link rows (named by the two entities in alphabetical order): `CalculationGeometryLink`, `GeometryTrajectoryLink`, `CalculationTrajectoryLink`, `StageStationaryLink`, `StepValidationLink`, and `IdentityStationaryLink`.
  - Existential data rows: `GeometryRow` (UUID primary key; `relabel_atoms` returns a new, unsaved row), `TrajectoryRow`, `ModelRow`, `CalculationRow`, `PropertyKindRow` (primary key `name`), `PropertyValueRow`, and `ValidationRow`.
  - Stationary point rows: `StationaryPointRow`.
  - Reaction network rows: `StageRow` and `StepRow` (`stage_id1 < stage_id2`, nullable `stage_id_ts` with a null-safe unique index).
  - Identity rows: `IdentityAlgorithmRow` (unique `name`, `kind`, `parent_algorithm_id`) and `IdentityRow` (unique `(algorithm_id, value)`).
- **`types.py`**: the lowest layer. `Role` (`StrEnum`: `input`/`output`), `CompressedArrayTypeDecorator(dtype=...)` (zlib-compressed `.npy`; `dtype=None` keeps the input dtype), and the decompression cap `MAX_DECOMPRESSED_BYTES`.

### Architectural rules

- **"If you own the data, you own the interface."** autogeom owns `Geometry` and its conversions; autostorage owns persistence and the identity registry. Never reimplement geometry logic here. Call autogeom (e.g. `autogeom.inchi(geo)`, `geo.xyz_block()`), and fix gaps upstream in autogeom.
- **Registries live in memory and are mirrored by name.** `IdentityAlgorithmRegistry` and `PropertyKindRegistry` are the source of truth. Their rows (`IdentityAlgorithmRow`, `PropertyKindRow`) are plain mirrors with unique names that are seeded when a `Database` opens. Look behavior (validation functions, dtypes) up from the registry by name. Never store behavior on a row (no Pydantic private attributes or shared row singletons).
- **Listeners**: register session-level listeners on `AutostorageSession`, never on the global `Session` class. Use mapper-level `before_insert`/`before_update` only to modify the target's own columns. Anything that touches another row must run in a session `before_flush` listener. Autoflush is off inside `before_flush`, so cache pending rows per flush (see `_IdentityFlushContext`).
- **Persistence models** are SQLModel `table=True` classes with a `Row` suffix (`GeometryRow`). Domain models (`autogeom.Geometry`, `IdentityAlgorithm`) have no suffix. Link tables are named `<EntityA><EntityB>Link`, alphabetically.
- Query with `session.exec(select(...))`, not the legacy `session.query(...)`.
- Schema changes are not migrated (pre-alpha). Call out breaking schema changes in the CHANGELOG.
- Keep `__all__` sorted, and expose the public API in `autostorage/__init__.py`.

## Code style

- **Naming**: modules are short singular nouns (`models`, `events`, `query`, `property`, `identity`, `types`). Instance variables use short abbreviations: `geo` (an `autogeom.Geometry`), `geo_row`, `stp` (stationary point), `calc`, `traj`, `ident`, `alg`, `sess`/`session`. Private helpers and constants use a leading `_`.
- Use relative imports inside the package (`from .models import GeometryRow`). Prefer `collections.abc` types (`Sequence`, `Collection`, `Mapping`) for parameters.
- Make boolean and option arguments **keyword-only** (`*, include_pseudo: bool = False`).
- Errors: assign the message, then raise: `msg = f"..."; raise SomeError(msg)`. Use `raise ... from err` when wrapping.
- `noqa` comments must name specific codes (`# noqa: ARG001`) and should say why when the reason isn't obvious.
- Group related definitions under short section comments (`# 1. Existential data rows`), with private helpers after the public functions they support. Write comments only to explain *why*, such as SQLAlchemy flush-order subtleties or constraint workarounds.

## Writing and documentation style

- **Docstrings**: use Google style (Ruff `pydocstyle` convention `google`), and give every module, class, and function a docstring. Start with a short imperative summary line ("Return a fresh session bound to this database's engine."). Leave types out of `Args:`, `Returns:`, and `Attributes:` because they come from annotations, and omit `Returns:` for functions that return `None`. List `Raises:` for documented exceptions. Row classes document their columns and relationships under `Attributes:` or with attribute docstrings. One-line docstrings are fine for private helpers and thin wrappers.
- **Doctests run** (`--doctest-modules` over `src` and `tests`). Examples in docstrings must be correct and runnable, or written as non-executed fenced blocks.
- **Prose**: be concise and technical, with backticked identifiers (`` `GeometryRow` ``), units stated explicitly (Angstroms, Hartree, `2S`), and em-dashes or colons for short asides. Explain design rationale briefly.
- **User docs**: Sphinx with MyST Markdown in `docs/source/` (`index.md`, `quickstart.md`, `models.md`, `database.md`). The API reference is generated by autodoc2 through a Napoleon (Google) parser. When the public API changes, update the relevant docs page, the `README.md`/`quickstart.md` usage examples, `examples/*.py`, the schema diagrams in `schema/` (re-render with `npx @pintora/cli render`), and the module map in `.claude/CLAUDE.md`.
- **CHANGELOG.md**: follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Record every user-facing change under `## [Unreleased]` in `### Added`, `### Changed`, `### Fixed`, or `### Removed`. Each entry is one bullet that names the exact API in backticks (with signature when helpful), followed by a brief what/why. **After completing any task, always update CHANGELOG.md with the changes made**, ensuring the entry is clear, concise, and follows the format of existing entries.
- **Commit messages**: short imperative subject lines ("Add IdentityAlgorithmRow and update IdentityRow with events"). Release commits (`Bump to X.Y.Z`) come from `pixi run release` (tbump). Don't bump versions by hand.

## Tests

- Tests live in `tests/test_<module>.py` (`test_database`, `test_events`, `test_models`, `test_query`, `test_types`), and `src/` doctests are also collected. Each module builds a temporary `Database` in a `database` fixture (`tmp_path` or `tempfile`). `tests/conftest.py` makes pytest skip the git-ignored `tests/scratch*` files.
- Give tests type hints and `-> None`, and a one-line docstring. Existing tests are grouped in `Test<Subject>` classes. Extend those in place, and name new standalone tests `test__<subject>_<behavior>`. Use `pytest.mark.parametrize` for case tables, `pytest.raises(..., match=...)` for errors, `pytest.warns(IdentityGenerationWarning, match=...)` for skipped identities, and `np.testing`/`pytest.approx` for floats.
- Use chemically valid geometries: autogeom rejects inconsistent spins (e.g. C+H with `spin=0`), and identity generation fails for unperceivable structures. Tests should pass under `-W error`.
- Coverage must stay ≥80% (branch coverage). Add tests with every new behavior.
- Run a single test with `pixi run -e dev pytest tests/test_events.py::TestClass::test_name`.

## Working against a local autogeom

`pixi run local start` switches `pixi.toml` to `autogeom = { path = "../autogeom" }` (lines marked `# local:true`/`# local:false`, see `scripts/local.sh`), and `pixi run local stop` switches back. Pre-commit runs `local stop` first. When bumping autogeom, update the pin in both `pixi.toml` and `pyproject.toml`, relock (`pixi install`), and read autogeom's CHANGELOG for removed or changed APIs.

## Pre-commit suite (lefthook)

`pixi run pre-commit` runs `lefthook run pre-commit --all-files`. These are the same hooks that run on `git commit` and in CI (`.github/workflows/test.yml`). The steps run in sequence:

1. `pixi run local stop`: switches `pixi.toml` back from local-dependency mode.
2. `pixi run fmt`: `ruff format .`
3. `pixi run lint`: `ruff check . --fix`, with `select = ["ALL"]` (only `COM812`, `TID252`, `D203`, `D213`, and `CPY001` are ignored; tests may use `assert`, and examples may also `print`).
4. `pixi run types`: `ty check` over `src` and `tests`.
5. `pixi run imports`: `lint-imports`, which enforces the `database` → `events` → `query` → `property` | `identity` → `models` → `types` layer contract.
6. `pixi run test`: `pytest`, including doctests, coverage with `fail_under = 80`, and an HTML report.
7. `git diff --exit-code`: fails if the working tree differs from the index. This catches files rewritten by `fmt`/`lint` and any unstaged edits.

**A task is not complete until `pixi run pre-commit` passes AND CHANGELOG.md has been updated.** Always run the pre-commit suite before declaring work done, and ensure every task updates the CHANGELOG with a clear entry describing the changes. The full suite takes only a few seconds.

- Fix the root cause of failures. Do not add blanket `noqa`/`type: ignore` comments, lower `fail_under`, or edit the lint configuration to get a pass.
- If `fmt` or `lint --fix` rewrites files, review the changes, stage them, and rerun until every step passes.
- Step 7 requires a clean diff against the index, so stage intended changes (`git add <files>`) before the final run. Don't commit unless asked.
- If `pixi.toml`/`pixi.lock` change, keep `pyproject.toml` dependencies in sync (`pixi run add <pkg>` edits `pyproject.toml` via uv).
