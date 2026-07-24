# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
### Added

- **`GeometryRow.geometry_hash`, `.find_or_create`**: A `sha256` hash of `symbols`/`coordinates`/`charge`/`spin`, backed by a unique constraint, plus a `find_or_create` classmethod (same `commit`-flag pattern as `ModelRow.find_or_create`) that reuses a matching row instead of inserting a duplicate. Only catches bit-identical content — a rotated/translated/jittered near-duplicate conformer still gets its own row.
- **Migration** for the new `geometry.geometry_hash` column: backfills existing rows before tightening to `NOT NULL` + unique, since SQLite can't add a populated column straight to that state.

### Changed

- **`Database.merge_from`**: `GeometryRow` is now deduplicated against the target's existing content (via `GeometryRow.find_or_create`), alongside `ModelRow` and non-auto-managed `IdentityRow`s.

### Fixed

- **Stationary/Hessian order-consensus revalidation**: Moved from per-instance `before_insert`/`before_update` mapper events (`validate_geometry_orders`) to a session-level `before_flush` listener (`revalidate_geometry_orders_on_insert_update`). The mapper event fired too late in the flush cycle to persist mutations to already-clean sibling `StationaryPointRow`s, so SQLAlchemy silently dropped those updates instead of writing them.
- **`_recompute_geometry_stationary_validity`**: Skips a `HessianRow` whose `.order` can't be computed yet (still pending its own shape validation later in the same flush) instead of raising the raw `ValueError`.

## [0.0.11] - 2026-07-23
### Added

- **`ModelRow.find_or_create`, `IdentityRow.find_or_create`**: Look up a matching row by content before creating one, with a `commit` flag (default `True`; pass `False` to only flush, leaving the caller's transaction open for staging several dedup lookups that must succeed or fail together). `unique_model`/`unique_identity` don't catch duplicates when a nullable column (`program_version`, `basis`) is `NULL`, since SQL treats `NULL` as distinct from itself in unique constraints — callers constructing and saving a fresh row each time (without every field set) were silently accumulating duplicate rows for the same logical model/identity, which broke downstream lookups keyed on `model_id`/`identity_id`.
- **`StageRow.find_or_create`, `StepRow.find_or_create`**: Same pattern as `ModelRow.find_or_create`, for stages and steps.
- **`BaseLink.create(*rows, **attrs)`**: Construct a link row by matching each positional row to its relationship by type (e.g. `CalculationGeometryLink.create(calc, geo, role=Role.INPUT)`), replacing the removed per-row `*_link()` wrapper methods below. Raises if a row's type matches more than one unfilled relationship (e.g. a link table with two relationships to the same row model), rather than silently picking one by declaration order.
- **`Database.merge_from(source_db, *, commit=True)`** (`autostorage.merge`, new module — `merge_databases()`, `MergeReport`): Copy another database's contents into this one, remapping ids/foreign keys and deduplicating content-unique rows (`ModelRow`, non-auto-managed `IdentityRow`s) against this database's existing data. InChI/conformer identities are deliberately left for `add_inchi_identities`/`assign_conformer_ids` (see `events.py`) to regenerate on insert, so matching conformers collapse onto one shared identity across the merged databases. Nothing commits until every table copies without error. Returns a `MergeReport` of rows copied/reused per table.
- **`GeometryRow.symmetry_number`**: Cached property (`functools.cached_property`) computing the molecular symmetry number from stereo-preserving graph automorphisms, via `stereomolgraph`. Safe to cache indefinitely since `symbols`/`coordinates` are immutable after insert (`verify_geometry_immutable_fields`).
- **`autostorage.utils.export_mess_input()`**: Render a sequence of `StepRow`s as MESS `Well`/`Bimolecular`/`Barrier` input blocks, with energies (electronic + harmonic ZPE, relative to a reference stationary point) and symmetry numbers (`GeometryRow.symmetry_number`) resolved from the database. A barrierless step's TS block has no geometry to compute a symmetry number from and gets a flagged `TODO(autostorage)` placeholder instead. Does not emit `Model`/`EnergyRelaxation`/`CollisionFrequency` blocks; the caller must prepend those.
- **`autostorage.utils.plot_pes()`, `PESPlot`**: Render the same step sequence as a potential energy surface diagram (a Matplotlib figure of level/connector segments along an unlabeled ordinal x-axis), with `PESPlot.save()` and Jupyter rich display (`_repr_png_`) support. A species/TS with no `EnergyRow` at the given model is drawn flagged (dashed, muted gray) rather than omitted.
- **`examples/stationary_point.py`**: Runnable end-to-end example building a synthetic water optimization + frequency workflow, touching every row model except `StageRow`/`StepRow` and their reaction-specific link tables.
- **`TimestampMixin`**: Adds server-managed `created_at`/`updated_at` columns to every `BaseRow` subclass.
- **`CalcStatus`**: Lifecycle status enum (`PENDING`/`RUNNING`/`SUCCEEDED`/`FAILED`) for a new `CalculationRow.status` column (default `PENDING`), paired with a new `CalculationRow.error_message` column.
- **`CompressedArrayTypeDecorator`**: Stores NumPy arrays as zlib-compressed `.npy` binary data, preserving shape and dtype for arrays of any dimensionality. Replaces `FloatArrayTypeDecorator`/`Float32BytesTypeDecorator` on `GeometryRow.coordinates`, `GradientRow.value`, and `HessianRow.value` — the latter previously stored a flattened, shapeless raw float32 buffer.
- **`StationaryPointRow.identity(kind=..., algorithm=...)`**: Return the first already-loaded identity matching kind and/or algorithm.
- **`CalculationRow.input_geometries`, `.output_geometries`, `.input_trajectories`, `.output_trajectories`**: Properties filtering linked geometries/trajectories by `Role`.
- **`Database.add_all()`**: Bulk counterpart to `add()`.
- **`Database.get_or_none()`**: Like `get()`, but returns `None` on a miss instead of raising.
- **`Database.exists()`**: Check whether any row matches a statement via a single `EXISTS` subquery, without materializing a match.
- **`Database.__enter__`/`__exit__`**: Support `with Database(...) as db:`; rolls back the session on an exception before closing.
- **`IdentityRow.unique_identity`**: Unique constraint on `(kind, algorithm, value)`.
- **Reverse-lookup and FK indexes**: Added to the trailing column of every composite-PK link table, to `ModelRow`/`StepRow` (null-safe unique indexes, since their existing unique constraints don't catch duplicates where a nullable column differs only by `NULL`), and to previously-unindexed foreign keys (`CalculationRow.model_id`, and `geometry_id`/`calculation_id` on `EnergyRow`, `GradientRow`, `HessianRow`, `StationaryPointRow`, `ValidationRow`).
- **Event listeners**: `verify_geometry_immutable_fields` (rejects changes to `GeometryRow.symbols`/`.coordinates` after insert), `verify_stage_ts_consistency` (validates a `StepRow`'s stages agree with it on transition-state status), `revalidate_geometry_orders_on_hessian_delete` (keeps `StationaryPointRow.is_valid` correct when the Hessian establishing order consensus is deleted).
- **Alembic migrations** (`migrations/`, `alembic.ini`, `pixi run migrate`): Evolve an existing on-disk database's schema in place, targeted via `AUTOSTORAGE_DATABASE_URL`; fresh/in-memory `Database` instances (including tests) are unaffected, still built via `create_all()`.

### Changed

- **`Database` engine**: JSON columns now serialize with sorted keys, so equality filters on JSON columns (e.g. `CalculationRow.input_provenance == prov`) match regardless of the dict's key insertion order.
- **`Database.exec_all()`**: Now returns a `list` instead of a lazy iterator.
- **`Database.flush()`**: Also expires all session objects, so an already-loaded object whose row was removed by a DB-level `ondelete="CASCADE"` during the flush reloads (or raises) on next access instead of reading back stale.
- **`Role` enum columns** (`CalculationGeometryLink.role`, `CalculationTrajectoryLink.role`): Store the enum's `.value` instead of its member name.
- **`ValidationRow.calculation_id`**: Now `NOT NULL` and indexed.
- **`HessianRow.harmonic_frequencies`**: Now a `functools.cached_property` instead of a plain `property`, since vibrational analysis re-diagonalizes the Hessian on every call and `.order` (used to recompute `StationaryPointRow.is_valid` for every sibling Hessian of a geometry, on every relevant flush) depends on it. Invalidated automatically on `.value` update by the new `invalidate_hessian_frequency_cache` event listener.
- **`matplotlib`, `stereomolgraph`**: Now required (not optional/dev-only) dependencies, for `plot_pes()`/`export_mess_input()` and `GeometryRow.symmetry_number` respectively.

### Fixed

- **`Database`**: `PRAGMA foreign_mode=DELETE` (not a valid SQLite pragma) corrected to `PRAGMA journal_mode=DELETE`, the intended WAL-mode fallback.
- **`GradientRow`/`HessianRow` shape validation, `StationaryPointRow`/`HessianRow` order validation, `StepRow` stage-consistency validation, `add_inchi_identities`, `assign_conformer_ids`**: Now resolve the target's geometry/relationship via the session when only the FK id was set (not the relationship itself), so validation and automatic identity attachment are no longer silently skipped in that case.
- **`ValidationRow`**: Removed a duplicate explicit `id` field that shadowed the one already provided by `BaseRow`.

### Removed

- **`BaseRow.save()` and `BaseLink.save()`**: Duplicated `Database.add()`/`Database.merge()` with a non-obvious "always commits" side effect. Use `db.add(row)` / `db.merge(row)` directly.
- **`GeometryRow.calculation_link()`, `.trajectory_link()`, `.stationary_point()`, `.energy()`, `.gradient()`, `.hessian()`**: Unused one-line wrappers around link/result-row constructors. Construct the row directly instead (e.g. `HessianRow(calculation=..., geometry=..., value=...)`).
- **`TrajectoryRow.geometry_link()`, `.calculation_link()`**: Unused one-line wrappers; construct the link row directly.
- **`CalculationRow.geometry_link()`, `.trajectory_link()`**: Unused one-line wrappers; construct the link row directly.

## [0.0.10] - 2026-07-17
### Added

- **`events.py`**: House custom `sqlalchemy` events.
  - **`assign_conformer_ids`**: Auto-tag duplicate conformers sharing an InChI with a shared `conformer`-kind `IdentityRow`.
- **`exc.py`**: Custom `Exception` classes.
- **`types.py`**: Custom typing.
  - **`CalcType`**: Normalize `CalculationRow.calc_type`.
- **`Database(wal=...)`**: Enable SQLite WAL journal mode.
- **`irmsd` dependency**: Conformer RMSD comparisons.

### Changed

- **Module refactor**:
  - `models/` -> `models.py` to consolidate logic and address circular import concerns.
- **`BaseRow`**: Provide a `.save()` method for standard auto-incremented ID tables.
- **`BaseHashedRow`**: Provide a `.resolve()` method for hashed tables, searching the database for matching hashes.
- **`BaseResultRow`**: Provide a `.query()` method for result tables (`EnergyRow`, `GradientRow`, `HessianRow`), searching the database for existing results.
- **`BaseLink`**: Provide a `.save()` method for non-incremented ID tables (e.g., links).
- **Table models**: Adjust fields and relationships on several models.
- **Dependency version**:
  - **`automol`**: Bump to `0.0.19`.
  - **`ty`**: Bump to `>=0.0.59,<0.0.60`.
- **`autostorage` layering**: Updated to `utils -> database -> events -> models -> types | exc`.
- **Supported platforms**: Restrict to `linux-64`; pin `python` to `>=3.12,<3.14`.

### Fixed

- **`tests`**: Reflect changes.

### Removed

- **`calculate` module** in favor of direct calls to `automol`.
- **`query.py` and `select.py`** in favor of class methods on table models.
- **`PartialMixIn`** due to type safety concerns.
- **`ComparisonMixIn`**.
- **`automatics` dependency** (discontinued package).
- **`qcdata` dependency** (no longer used).
- **`examples` directory**.

## [0.0.9] - 2026-06-18
### Added
- `calculate` module for calculating properties of database rows.
- `GradientRow` and `HessianRow` for storing respective values.
- Event listeners for validating shape of gradient and Hessian values.
- `ValidationRow` for assocating validation calculations (such as `Intrinsic Reaction Coordinate`) with elementary steps.
- `ModelRow.hash` (from `automatics`) as a unique constraint.
- `query` module combining `select` statements and `db.exec` methods for convenience.
- `xyzrender` as a dev / optional dependency.

### Changed
- Bump `automatics` to v0.0.6,
- Bump `automol` to v0.0.16.

### Fixed
- Tests to reflect changes.

### Removed
- `read` module in favor of class methods.

## [0.0.8] - 2026-06-12
### Added

- **`BaseRow` model**: Manage universal attributes and mixin methods across all row models.
- **`ComparisonMixin`**: Define equivalency behavior between database rows without including row IDs.
- **`IdentityExtraRow`**: Tag identities with non-queryable attributes (e.g., SMILES strings).
- **`select` module**: Convenience methods for generating `SelectOfScalar` objects.
- **`database.get()`**: Retrieve a row from the database by ID.
- **`database.exec` methods**: Return first, all, or one match to a `SelectOfScalar` query.
- **`read` module**: Read common file types (e.g., '.xyz') into database instances.
- **`automatics` dependency**: Maintain a single source of truth for core `autosuite` objects.
- **`ModelRow`**: Store pertinent information about a calculation model.
- **`TrajectoryRow`, `StageRow`, `StepRow`**: Define input/output relationships between `GeometryRow`, `StationaryPointRow`, and `CalculationRow`.

### Changed

- **Module refactor**: 
  - `Calculation` and related modules exported to `automatics` as `Model`.
- **CalculationRow**: Store provenance and IDs of input/output `GeometryRow` and `TrajectoryRow` entries.
- **Dependency version**:
  - **`automol`**: Bump to `0.0.14`.
- **`autostorage` layering**.
- **Model organization**:
  - **`geom` module**: Models related to molecular geometries.
  - **`calculation`**: Models related to calculation inputs and outputs.

### Removed

- **`db.find()` and `db.find_or_add()`**.


### Fixed

- **`Database.session()`**: Yield a persistent session.
- References to `AutoStore`.


## [0.0.7] - 2026-04-30
- Renames library to "AutoStorage" to avoid PyPI name conflicts
- Exposed lower-level types and utilities to the top-level import

## [0.0.6] - 2026-04-27
- Explicitly set the Pixi Ty version to match the current marketplace extension.

- Added database convenience methods:
  - row_to_dict() for serializing rows to dictionaries (optionally including default fields)
  - verify_single_iteration() to ensure Database.find() returns exactly one RowModel

- Updated Database behavior:
  - All methods (except delete()) now return full SQLModel objects instead of RowIDs
  - Added eager_load parameter to add() and find() to include relationships on returned objects
  - Introduced find_or_add() as a convenience wrapper (find() → add() if no match)
  - Replaced query() entirely with find(), which accepts partially or fully populated models

- Introduced partial model support:
  - RowModel.partial(**attrs) allows constructing models with missing required fields for querying
  - Implemented via autostore.models.optional using a PartialMixin

- Refactored model structure:
  - Split autostore/models.py into autostore/models/* for improved organization
  - Separated provenance data into a new ProvenanceRow
  - Shortened some lengthy model attribute names.
  - Standardized model attributes to snake_case

- Refined domain models and logic:
  - CalculationRow.calc_type changed from str → str | None to reduce redundancy (handled at lower levels)
  - Updated calcn.core.project to avoid mutating original Calculation instances
  - Updated calcn.core.hash_full to reflect CalculationRow refactor

- Simplified module structure:
  - Removed standalone autostore/qc
  - Moved relevant functionality onto row models (CalculationRow, ProvenanceRow, GeometryRow)

- StationaryPointRow now cascade-deletes when linked GeometryRow or CalculationRow is deleted

- Reworked test suite to improve modular testing and debugging

## [0.0.5] - 2026-04-09
### Added
- Added superprogram fields to CalculationRow.
- Updated qc interfaces to reflect update from qcio -> qcdata
- Database row models moved from models/* to models.py
- Added Database methods for adding, getting, and querying rows from database
- CalculationGeometryLink table to associate Calculation with input/output Geometries
  - Calculation Geometries can be accessed by CalculationRow.geometries
  - Geometry Calculations can be accessed by GeometryRow.calculations
- Placeholder MetricRow for storing identifying properties




## [0.0.4] - 2026-04-01

## [0.0.3] - 2026-01-29
### Added
- Geometry hash field populated by event listener
- Calculation object with hash registry
- Calculation hash table populated by event listener
- Interconversion of Calculation and QCIO ProgramInput objects
- Read energy from database

### Fixed
- Specify Calculation-Energy and Geometry-Energy as many-to-one relationships
- Uniqueness constraint in CalculationHashRow

## [0.0.2] - 2026-01-28
### Added
- `qc` submodule for interconversion with `QCIO` objects

### Fixed
- Fix coordinate units (Angstrom) in geometry table

## [0.0.1] - 2026-01-28
### Added
- Write energy to database
