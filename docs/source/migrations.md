# Migrations

`autostorage` has two independent sources of schema, used in different situations:

- **`SQLModel.metadata.create_all(engine)`** — runs automatically inside
  {py:meth}`Database.__init__ <autostorage.database.Database.__init__>` and builds the full
  current schema from the model definitions in one shot. This is what fresh and in-memory
  databases use, including every `Database` instance created in the test suite. No Alembic
  involvement at all.
- **Alembic migrations** (`migrations/`) — the only path for evolving an *existing* on-disk
  database in place, so it picks up schema changes without losing the data already in it.

If you're not migrating an existing database (e.g. writing a test, or working with a
scratch/in-memory `Database`), you don't need anything on this page — just change the models
and `create_all` picks it up.

## Applying migrations

```bash
AUTOSTORAGE_DATABASE_URL=sqlite:///path/to.db pixi run migrate
```

`pixi run migrate` runs `alembic upgrade head`. `migrations/env.py` reads
`AUTOSTORAGE_DATABASE_URL` from the environment and uses it to override `alembic.ini`'s
`sqlalchemy.url` at runtime, so a single Alembic setup can target any on-disk database without
editing config. If the variable isn't set, Alembic falls back to whatever's hardcoded in
`alembic.ini`.

`env.py` also does one thing that's easy to miss: it imports `autostorage.database` purely for
its side effect of pulling in `autostorage.models` and `autostorage.events`, which is what
registers every `table=True` model onto `SQLModel.metadata`. Without that import, Alembic
would see an empty target schema.

## Writing a new migration

After changing a `table=True` model's columns, constraints, or indexes:

```bash
pixi run -e dev alembic revision --autogenerate -m "describe the change"
```

Run this against a scratch on-disk SQLite database (not `:memory:` — Alembic needs a real file
to diff against), then **review the generated script by hand** before committing it. Alembic's
autogenerate is a reasonable first draft, not a guarantee — see the caveat below for one gap
specific to this schema.

### SQLite can't reflect expression-based indexes

Two constraints in `models.py` are implemented as expression-based unique `Index`es rather than
plain `UniqueConstraint`s, specifically to make them null-safe (SQL treats `NULL != NULL`, so a
plain `UniqueConstraint` lets multiple "duplicate" rows through whenever one of the constrained
columns is `NULL`):

- `unique_model_null_safe` on `ModelRow`, over `(program, coalesce(program_version, ''),
  method, coalesce(basis, ''))`.
- `unq_step_stages_null_safe` on `StepRow`, over `(stage_id1, stage_id2, coalesce(stage_id_ts,
  0))`.

SQLite's reflection support can't see expression-based indexes, so `alembic revision
--autogenerate` silently omits them from the generated script — it isn't that it gets them
wrong, it just doesn't know they exist. If a migration touches `model` or `step`, check whether
these indexes need to be re-created by hand, following the pattern already used in
`e50de3129c84_add_null_safe_indexes_reverse_lookup_.py`:

```python
op.create_index(
    "unique_model_null_safe",
    "model",
    [
        "program",
        sa.text("coalesce(program_version, '')"),
        "method",
        sa.text("coalesce(basis, '')"),
    ],
    unique=True,
)
```

Both indexes are also defense-in-depth alongside an app-level lookup that's the actual
dedup mechanism in practice — `ModelRow.find_or_create` and `StepRow.find_or_create`/`.query`
(see [Data model](data-model.md)) — so a missed index mainly risks a duplicate row slipping in
under a race, not a functional bug in normal single-writer use.

## Migration history

```{list-table}
:header-rows: 1

* - Revision
  - Down revision
  - Summary
* - `faa9f50bc029`
  - (base)
  - Baseline: the schema as of the first tracked migration.
* - `e50de3129c84`
  - `faa9f50bc029`
  - Adds `created_at`/`updated_at` timestamps across tables, `CalculationRow.status`/
    `error_message`, reverse-lookup indexes on several link tables, and the two null-safe
    expression indexes described above.
```

## Keeping migrations and models in sync

`tests/test_migrations.py` guards against migrations drifting from the current model
definitions: it applies every migration to a scratch database with `alembic upgrade head`, then
uses `alembic.autogenerate.compare_metadata` to diff the result against `SQLModel.metadata` and
asserts there's no difference. If you change a model without writing (or correctly writing) the
matching migration, this test fails — treat it as the source of truth for whether a migration
is complete, not just `alembic revision --autogenerate` running without error.
