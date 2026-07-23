# Data model

autostorage stores a workflow as a graph of related rows rather than a single flat table.
This page describes the module layout, the row/link types that make up the schema, and the
automatic behaviors that keep the graph consistent.

## Module layering

`autostorage` is a flat module structure (no sub-packages), with a strict dependency order
enforced by import-linter — higher layers may depend on lower ones, never the reverse:

```
autostorage.utils               (highest)
autostorage.database
autostorage.events
autostorage.models
autostorage.types | autostorage.exc   (lowest)
```

- {py:mod}`autostorage.types` — enums (`CalcType`, `CalcStatus`, `Role`) and
  `CompressedArrayTypeDecorator`, which stores NumPy arrays as zlib-compressed `.npy` bytes
  so gradients, Hessians, and coordinates round-trip through SQLite without precision loss.
- {py:mod}`autostorage.exc` — `ResultShapeError`, `MissingPrimaryKeyError`.
- {py:mod}`autostorage.models` — the SQLModel row/link definitions described below.
- {py:mod}`autostorage.events` — SQLAlchemy ORM event listeners that validate and enrich rows
  as they flow through a session.
- {py:mod}`autostorage.database` — `Database`, the SQLite engine/session manager applications
  interact with directly.

## Relationship to automol

Row models extend `automol`'s core data models directly rather than wrapping them:
`GeometryRow` extends `automol.Geometry`, `IdentityRow` extends `automol.Identity`. Any
conversion to/from other external formats is delegated to `automol`'s own conversion functions
rather than reimplemented here.

## Core rows

| Row | Represents |
| --- | --- |
| `GeometryRow` | A molecular geometry (symbols, coordinates, charge, spin). |
| `IdentityRow` | A chemical identifier (InChI, SMILES, conformer group, ...) shared across stationary points. |
| `IdentityExtraRow` | Extra key/value metadata attached to an `IdentityRow`. |
| `TrajectoryRow` | An ordered sequence of geometries (e.g. an optimization or IRC path). |
| `StationaryPointRow` | A stationary point on a PES — a geometry plus Hessian order and validity. |
| `StageRow` | A chemical state (reactant, product, or transition state) in a reaction. |
| `StepRow` | An elementary reaction step connecting two `StageRow`s, optionally via a TS stage. |
| `ModelRow` | A calculation model spec (program, program version, method, basis). |
| `CalculationRow` | A single quantum-chemistry calculation: type, status, provenance. |
| `ValidationRow` | A validation calculation (e.g. IRC) performed on a `StepRow`. |
| `EnergyRow` / `GradientRow` / `HessianRow` | Results computed at a geometry by a calculation. |

`BaseRow` (id + `created_at`/`updated_at` timestamps) is the base for all of the above except
link tables. Result rows additionally share `BaseResultRow`, which provides the `query()`
classmethod for looking a result up by geometry, model, and input provenance.

## Link tables

Many-to-many and role-tagged relationships go through dedicated link rows (`BaseLink`), each
with a composite primary key and `ondelete="CASCADE"` foreign keys:

- `CalculationGeometryLink` / `CalculationTrajectoryLink` — tag a geometry/trajectory as
  `Role.INPUT` or `Role.OUTPUT` for a calculation.
- `TrajectoryGeometryLink` — orders geometries within a trajectory.
- `StationaryIdentityLink` — attaches identities to a stationary point.
- `StationaryStageLink` — groups stationary points into a `StageRow`.
- `StepValidationLink` — attaches validations to a `StepRow`.

`BaseLink.create(*rows, **attrs)` builds a link by matching each row to the relationship whose
type it satisfies, so callers don't need to know the link's field names:

```python
link = CalculationGeometryLink.create(calc, geo, role=Role.INPUT)
```

## Automatic behavior (event listeners)

`autostorage.events` registers SQLAlchemy listeners that run on flush, so these behaviors apply
regardless of how a session is driven:

- **Shape validation** — `GradientRow.value` must be `(3 * atom_count,)` and `HessianRow.value`
  must be `(3 * atom_count, 3 * atom_count)` for their linked geometry, or a
  `ResultShapeError` is raised.
- **Stationary-point validity** — when a `HessianRow` is inserted, updated, or deleted,
  `StationaryPointRow.is_valid` is recomputed from consensus among the geometry's Hessians
  (comparing each stationary point's declared `order` to the Hessian-derived order).
- **Geometry immutability** — `symbols`/`coordinates` cannot be changed on a `GeometryRow`
  after it's been inserted, since doing so would silently invalidate shape checks already run
  against it. `charge`/`spin` remain mutable.
- **Automatic identity attachment** — new `StationaryPointRow`s get InChI and SMILES
  `IdentityRow`s attached automatically via `automol.Algorithm`, deduplicated against existing
  identity rows.
- **Conformer grouping** — new stationary points are compared against InChI peers using
  `automol.geom.is_duplicate_conformer`; a match reuses the peer's conformer-group identity,
  otherwise a new group id is allocated.
- **Reaction step consistency** — `StepRow.stage_id1`/`stage_id2` are kept in sorted order (to
  satisfy the `stage_id1 < stage_id2` check constraint), `is_barrierless` is derived from
  whether `stage_id_ts` is set, and `stage1`/`stage2` are rejected if they reference a
  transition-state stage (and vice versa for `stage_ts`).

## Migrations

`migrations/` holds Alembic migrations, wired to `SQLModel.metadata`. This only applies to
evolving an *existing* on-disk database in place — fresh or in-memory `Database` instances
(including every test) get their schema from `SQLModel.metadata.create_all` directly, no
migration involved.

Any change to a `table=True` model's columns/constraints/indexes needs a matching Alembic
revision. SQLite can't reflect the expression-based null-safe unique indexes on
`ModelRow`/`StepRow` (e.g. `unique_model_null_safe`, `unq_step_stages_null_safe`), so
`alembic revision --autogenerate` silently skips those — they must be added to new migrations
by hand if those models are ever touched again.
