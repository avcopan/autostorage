# Database

{py:class}`~autostorage.database.Database` is the single entry point applications use to open
a SQLite file, get schema created, and run queries and mutations against it. This page covers
its connection semantics and the full method surface; see [Quickstart](quickstart.md) for a
minimal end-to-end example and [Data model](data-model.md) for what gets stored.

## Opening a database

```python
from autostorage import Database

db = Database("workflow.db")       # created if it doesn't exist
db = Database(":memory:")          # scratch, in-process, gone on close()
db = Database("workflow.db", echo=True, wal=True)
```

- `path` — a filesystem path (`str` or `Path`) or SQLite's special `:memory:` name.
- `echo` — when `True`, every SQL statement is logged to stdout (passed straight through to
  SQLAlchemy's `create_engine`).
- `wal` — when `True`, attempts `PRAGMA journal_mode=WAL` on connect for better concurrent
  read/write throughput; if the backend rejects it, it falls back to `PRAGMA
  journal_mode=DELETE` (SQLite's default) rather than failing to connect.

On every new DBAPI connection, `Database` also unconditionally issues `PRAGMA
foreign_keys=ON` — SQLite disables foreign-key enforcement by default, and the `ON DELETE
CASCADE` behavior the schema relies on (see [Link tables](data-model.md#link-tables)) depends
on this being set.

`__init__` also calls `SQLModel.metadata.create_all(self.engine)`, so a fresh or in-memory
`Database` gets its full schema immediately — no Alembic migration is involved for these cases.
See [Migrations](migrations.md) for evolving an *existing* on-disk database instead.

### JSON key ordering

The engine is configured with a custom `json_serializer` that sorts dict keys
(`json.dumps(..., sort_keys=True)`). SQLite compares JSON columns as opaque text, so without
this, two Python dicts with the same key/value pairs but different insertion order would
serialize to different strings and fail to match in a query like:

```python
CalculationRow.input_provenance == {"seed": 1, "source": "orca"}
```

This affects any JSON-backed column: `CalculationRow.input_provenance`/`output_provenance`,
`ValidationRow.extras`, `GeometryRow.symbols`, and `TrajectoryGeometryLink.index`.

## Session model and thread-safety

`Database` opens exactly one long-lived `Session` in `__init__` and reuses it for every method
call — `session()` is a context manager that yields that same session rather than creating a
fresh one per call. This matters in two ways:

- Rows returned from a query stay attached to the session after the call returns, so
  lazy-loaded relationships (e.g. `energy.geometry`, `calc.model`) keep working afterward.
- A `Database` instance is **not safe for concurrent use by multiple threads.** The engine is
  created with `connect_args={"check_same_thread": False}`, but that only lifts SQLite's
  restriction on using the underlying DBAPI connection from a different thread than it was
  opened on (e.g. handing the whole `Database` off to a single background worker thread) — it
  does not make the `Session` itself safe for concurrent access. Two threads calling methods on
  the same `Database` at the same time is unsupported.

If an operation raises inside the `session()` context manager, the session is rolled back
before the exception propagates, so a failed call doesn't leave partially-staged changes behind
for the next call.

## Opening and closing

```python
db = Database("workflow.db")
...
db.close()
```

`close()` disposes the underlying engine (and its connection pool). `Database` also supports
the context-manager protocol:

```python
with Database("workflow.db") as db:
    ...
```

On a clean exit this just calls `close()`. If the `with` block raises, the session is rolled
back first, then closed — so an exception partway through a multi-step workflow can't leave
uncommitted changes lingering in the session.

## Writing rows

```python
db.add(row)             # stage a single row
db.add_all([row1, row2])  # stage multiple rows
db.commit()              # write staged changes, commit the transaction
```

`add`/`add_all` only **stage** rows in the session — nothing is validated or written to the
database until the next `flush()` or `commit()`. This means integrity errors (unique constraint
violations) and the shape-validation event listeners (see [Events](events.md)) raise at that
later point, not at the `add` call site.

```python
db.flush()
```

Flushes pending changes without committing the transaction — useful for surfacing
validation/integrity errors early, or for getting DB-assigned values (like an autoincrement
`id`) onto an object before you need to reference it. Unlike `commit()`, `flush()` doesn't
trigger SQLAlchemy's `expire_on_commit` behavior, so it follows up with `session.expire_all()`
— otherwise an already-loaded object whose row was removed by a `ON DELETE CASCADE` during this
flush would read back stale (pre-deletion) data on next access instead of raising.

```python
merged = db.merge(row)
```

`merge()` copies the state of a (possibly detached) row onto the identity-matched row already
tracked by the session — or inserts it if there is none — commits, and returns the merged
instance. Use this instead of `add()` when you're not sure whether the row is already attached
to this session's identity map (e.g. it was loaded by a different `Database`/session, or
round-tripped through serialization).

```python
db.delete(row)
```

Deletes a row and commits immediately (there's no separate staged-delete-then-flush step, since
`add`/`add_all` are the only staging-only methods).

## Reading rows

By primary key:

```python
row = db.get(GeometryRow, 3)         # raises LookupError if missing
row = db.get_or_none(GeometryRow, 3)  # returns None if missing
```

By a `select()` statement (from `sqlmodel`, or the `SelectStatement`/`Select`/`SelectOfScalar`
aliases re-exported from `autostorage.database`):

```python
from sqlmodel import select
from autostorage import CalcType, CalculationRow

stmt = select(CalculationRow).where(CalculationRow.calc_type == CalcType.ENERGY)

db.exec_first(stmt)  # first match, or None
db.exec_one(stmt)    # the single match; raises LookupError on zero or >1 matches
db.exec_all(stmt)    # list of all matches
db.exists(stmt)      # bool, via a single EXISTS subquery — never materializes a row
```

`exec_one` wraps SQLAlchemy's `NoResultFound`/`MultipleResultsFound` and re-raises both as
`LookupError`, so callers only need to handle one exception type regardless of which way the
query failed to return exactly one row.

Most model classes also expose their own `query()`/`find_or_create()` classmethods built on
top of these primitives (e.g. `ModelRow.find_or_create`, `EnergyRow.query`,
`StationaryPointRow.query`) — prefer those where available, since they encode the right lookup
key for that row type. See [Data model](data-model.md) for the full list.

## Exceptions raised through `Database`

- `LookupError` — from `get()` (missing id) and `exec_one()` (zero or multiple matches).
- `autostorage.exc.MissingPrimaryKeyError` — raised by model `query()`/`find_or_create()`
  methods when a row passed in hasn't been persisted yet (no `id`), since the query can't be
  built without one. Call `db.add()`/`db.merge()` and `db.commit()`/`db.flush()` first.
- `autostorage.exc.ResultShapeError` — raised on `flush()`/`commit()` if a `GradientRow` or
  `HessianRow` value doesn't match the shape implied by its geometry's atom count. See
  [Events](events.md#shape-validation).
- SQLAlchemy's `IntegrityError` — for constraint violations (unique constraints, `NOT NULL`,
  `CheckConstraint`s) that reach the database itself rather than being caught by an app-level
  `query()`/`find_or_create()` lookup first.
