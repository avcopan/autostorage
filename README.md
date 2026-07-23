# autostorage

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Pixi Badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json)](https://pixi.sh)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Typing: ty](https://img.shields.io/badge/typing-ty-EFC621.svg)](https://github.com/astral-sh/ty)

A [SQLModel](https://sqlmodel.tiangolo.com/)/SQLAlchemy persistence layer for computational chemistry workflow data, built on top of [`automol`](https://github.com/avcopan/automol). It stores molecular geometries, chemical identities, trajectories, stationary points, calculation results (energies, gradients, Hessians), and the calculations/reaction steps that connect them, as a graph of related rows in a SQLite database.

Row models extend `automol`'s core data models directly rather than wrapping them — `GeometryRow` extends `automol.Geometry`, `IdentityRow` extends `automol.Identity` — so any data already expressed in `automol` types can be persisted with no conversion step.

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

`Database` also supports the `with` statement, which rolls back on an unhandled exception and closes the connection on exit:

```python
with Database("workflow.db") as db:
    ...
```

Two databases can be combined with `Database.merge_from()`, which copies every row from one into the other, remapping ids/foreign keys and deduplicating content-unique rows (models, non-auto-managed identities) against the target's existing data:

```python
with Database("combined.db") as target, Database("other.db") as other:
    report = target.merge_from(other)
    print(report.copied, report.reused)  # per-table row counts
```

For a full worked example covering geometries, trajectories, results, and identities, see [`examples/stationary_point.py`](examples/stationary_point.py). Reaction networks (`StageRow`/`StepRow`) can be exported as [MESS](https://tcg.cse.anl.gov/papr/codes/mess.html) input via `autostorage.utils.export_mess_input()`, or rendered as a potential energy surface diagram via `autostorage.utils.plot_pes()`.

See `CLAUDE.md` for the full module map and architecture notes.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the [MIT License](LICENSE).
