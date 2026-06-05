# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
### Add

- **Database execution API**
    - `Database.get(model=..., row_id=...)`: Fetch database models by ID.
    - `Database.exec_first()`, `Database.exec_one()`, and `Database.exec_all()`: Execute SQLModel Select statements.
- **SQLModel Select factories**:
    - `select.matching_rows()` and `select.linked_rows()`: Conveniently generate SQLModel Select statements.
- **Row models**:
    - `TrajectoryRow`, `CalculationTrajectoryLink`, and `GeometryTrajectoryLink`: Store ordered outputs of a single calculation and establish relationships to `calculation` and `geometry` tables.
- **`BaseRow` model**: Manage universal attributes and mixin methods across all row models.
- **`ComparisonMixin`**: Define equivalency behavior between database rows without including row IDs.
- **`IdentityExtraRow`**: Tag identities with non-queryable attributes (e.g., SMILES strings).
- **`utils.iterator`**: Operate on iterables, such as `iterator.is_empty()`.

### Change

- **Module refactors**: 
  - `database` -> `database.core`.
  - `models.optional` -> `models.base`.
- **Documentation**: Model docstrings explicitly mark SQL Relationship attributes with `[SQL]`.
- **Listeners**: `on_stationary_point_insert` listener to implement `automol.Identity`.
- **Testing**: Test suite to reflect recent refactors and additions.

### Remove

- **Database execution API**: `Database.find()` and `Database.find_or_add()`.
- **Data parsing methods**: 
    - `CalculationRow.program_input()`, `CalculationRow.from_program_output()`, `ProvenanceRow.from_program_output()`: Separate data parsing responsibilities from core package.
    - `GeometryRow.structure()`, `GeometryRow.from_structure()`: Refactor Geometry methods into `automol`.
- **`utils.sqlalchemy.row_to_dict()`**: Encourage `BaseRow.model_dump(include=..., exclude=...)`.

### Fix

- **`Database.session()`**: Yield a persistent session.
- **`automol`**: Bump to `0.0.13`.

### Security

- **Move `SQLModelT` `TypeVar` to `models.base`**: Resolve a circular import issue.
- **Reconfigure layering**: Ensure `types.*` remains the lowest-level dependency.


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
