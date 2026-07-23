# Quickstart

## Installation

Install as a [Pixi](https://pixi.sh) dependency:

```toml
[dependencies]
autostorage = ">=0.0.10"
```

Or with `uv`/`pip` from PyPI:

```bash
uv add autostorage
```

Requires Python ≥3.12.

## Usage

```python
import numpy as np
from autostorage import (
    CalcType,
    CalculationGeometryLink,
    CalculationRow,
    Database,
    EnergyRow,
    GeometryRow,
    ModelRow,
    Role,
)

# Open (or create) a SQLite database; ":memory:" also works for scratch use.
db = Database("workflow.db")

# `find_or_create` dedups on (program, program_version, method, basis).
model = ModelRow.find_or_create(db, program="orca", method="b3lyp", basis="def2-svp")

calc = CalculationRow(model=model, calc_type=CalcType.ENERGY)
geo = GeometryRow(
    symbols=["H", "O", "H"],
    coordinates=np.array([[0, 0, 0.8], [0, 0, 0], [0.8, 0, 0]]),
    charge=0,
    spin=0,
)
link = CalculationGeometryLink.create(calc, geo, role=Role.INPUT)
db.add_all([model, calc, geo, link])
db.commit()

# Attach a result to the geometry/calculation pair.
energy = EnergyRow(geometry=geo, calculation=calc, value=-76.02)
db.add(energy)
db.commit()

# Look the result back up by geometry, model, and input provenance.
found = EnergyRow.query(db, geo=geo, model=model)
assert found is not None
print(found.value)

db.close()
```

`Database` also supports the `with` statement, which rolls back on an unhandled exception and
closes the connection on exit:

```python
with Database("workflow.db") as db:
    ...
```

## Migrating an existing database

Fresh or in-memory `Database` instances get their schema from `SQLModel.metadata.create_all`
automatically — no migration step needed. For an existing on-disk database, apply
[Alembic](https://alembic.sqlalchemy.org/) migrations with:

```bash
AUTOSTORAGE_DATABASE_URL=sqlite:///path/to.db pixi run migrate
```

See [Data model](data-model.md) for the schema this creates, and the
{doc}`API reference <apidocs/index>` for full details on every model and method.
