# Quickstart

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

The `Database.session()` method returns a standard SQLAlchemy `Session` that supports the
context manager protocol. Sessions automatically handle transaction management — commit
explicitly to persist changes, and unhandled exceptions trigger a rollback.

See the {doc}`API reference <apidocs/index>` for full details on every model and method.
