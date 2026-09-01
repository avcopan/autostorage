# Data Models

autostorage uses SQLModel/SQLAlchemy to define a relational schema for computational chemistry workflow data. The models form a graph structure where molecular geometries, calculations, stationary points, and chemical identities are linked through explicit relationship tables.

## Model Overview

The schema is organized into five functional groups:

### Link Tables

Association tables implementing many-to-many relationships between entities.

| Model | Description |
|-------|-------------|
| `CalculationGeometryLink` | Associates geometries with calculations, tracking whether each geometry is an input or output |
| `GeometryTrajectoryLink` | Links geometries to trajectories with position indices |
| `CalculationTrajectoryLink` | Associates trajectories with calculations as inputs or outputs |
| `StageStationaryLink` | Connects stationary points to reaction stages |
| `StepValidationLink` | Links validation calculations to reaction steps |
| `IdentityStationaryLink` | Associates chemical identities with stationary points |

### Core Data Models

The fundamental entities representing molecular structures, calculations, and their results.

| Model | Description |
|-------|-------------|
| `GeometryRow` | Molecular geometry with atomic symbols, coordinates, charge, and spin; extends `automol.Geometry` |
| `TrajectoryRow` | Ordered sequence of geometries from a dynamic calculation |
| `ModelRow` | Calculation model specification (program, method, basis set, keywords) |
| `CalculationRow` | Quantum chemistry calculation with provenance metadata |
| `EnergyRow` | Energy result for a geometry at a specific level of theory |
| `GradientRow` | Energy gradient (forces) for a geometry |
| `HessianRow` | Second derivative matrix (Hessian) for a geometry |
| `ValidationRow` | Validation result (e.g., IRC) for a reaction step |

### Stationary Points

Models representing critical points on potential energy surfaces.

| Model | Description |
|-------|-------------|
| `StationaryPointRow` | A stationary point with Hessian index and validation status |

### Reaction Network

Models defining elementary reaction steps and their constituent chemical states.

| Model | Description |
|-------|-------------|
| `StageRow` | A chemical state in a reaction (reactant, product, or transition state) |
| `StepRow` | An elementary reaction step connecting two stages via a transition state (or barrierless) |

### Chemical Identities

Models for chemical identification and classification.

| Model | Description |
|-------|-------------|
| `IdentityRow` | Queryable chemical identifiers (InChI, AmChI, etc.) with kind and algorithm; extends `automol.Identity` |
| `IdentityExtraRow` | Additional *non-queryable* identities (SMILES, Hill formula, ...) attached to a primary identity |

## Design Principles

- **automol integration**: `GeometryRow` and `IdentityRow` extend `automol.Geometry` and `automol.Identity` directly rather than wrapping them, delegating all format conversions to automol
- **Explicit relationships**: Many-to-many relationships use dedicated link tables rather than implicit joins
- **Provenance tracking**: Calculations record both input and output provenance metadata
- **Compressed storage**: NumPy arrays (coordinates, gradients, Hessians) are stored as zlib-compressed binary data via `CompressedArrayTypeDecorator`
- **Graph structure**: The schema forms a directed graph where calculations consume and produce geometries/trajectories, geometries carry results, stationary points reference geometries, and reaction steps connect stages
