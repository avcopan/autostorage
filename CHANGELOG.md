# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
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
