# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.0.8] - 2026-06-12
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
- Write energy to database# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
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
