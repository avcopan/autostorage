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
autostorage = ">=0.0.12"
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

# Work within a session context.
with db.session() as session:
    # Create a model specifying the calculation type, program, method, and basis.
    model = ModelRow(
        calc_type="energy",
        program="orca",
        method="b3lyp",
        basis="def2-svp",
    )

    # Create a calculation using this model.
    calc = CalculationRow(model=model)

    # Create a geometry.
    geo = GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 0.8], [0, 0, 0], [0.8, 0, 0]]),
        charge=0,
        spin=0,
    )

    # Link the geometry to the calculation as an input.
    link = CalculationGeometryLink(
        calculation=calc,
        geometry=geo,
        role=Role.INPUT,
    )

    # Add all objects to the session and commit.
    session.add_all([model, calc, geo, link])
    session.commit()

    # Attach an energy result to the geometry/calculation pair.
    energy = EnergyRow(geometry=geo, calculation=calc, value=-76.02)
    session.add(energy)
    session.commit()

    # Query the result back by filtering on geometry and calculation.
    found = session.query(EnergyRow).filter_by(
        geometry_id=geo.id,
        calculation_id=calc.id,
    ).first()
    assert found is not None
    print(found.value)

db.close()
```

`Database.session()` returns a standard SQLAlchemy `Session` that supports the context manager protocol. Sessions don't commit automatically — call `session.commit()` explicitly to persist changes.

For a full worked example covering geometries, trajectories, results, stationary points, stages, and steps, see [`examples/stationary.py`](examples/stationary.py).

See [CLAUDE.md](.claude/CLAUDE.md) for the full module map and architecture notes, or the [Sphinx docs](docs/source) for a rendered quickstart and API reference.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the [MIT License](LICENSE).
