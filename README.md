# autostorage

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Pixi Badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json)](https://pixi.sh)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Typing: ty](https://img.shields.io/badge/typing-ty-EFC621.svg)](https://github.com/astral-sh/ty)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-border.json)](https://github.com/copier-org/copier)

A [SQLModel](https://sqlmodel.tiangolo.com/)/SQLAlchemy persistence layer for computational chemistry workflow data, built on top of [`autogeom`](https://github.com/avcopan/autogeom). It stores molecular geometries, chemical identities, trajectories, stationary points, calculation results (energies, gradients, Hessians), and the calculations/reaction steps that connect them, as a graph of related rows in a SQLite database.

`GeometryRow` extends `autogeom.Geometry` directly rather than wrapping it, so a `Geometry` can be persisted with no conversion step, and autogeom's functions accept the rows directly. Chemical identities (InChI, SMILES, Hill formula) are generated automatically for stationary points by the algorithms in `IdentityAlgorithmRegistry`, to which you can add your own.

## Installation

autostorage requires Python 3.13 or later.
With [Pixi](https://pixi.sh), add it from the [`avcopan/automech`](https://prefix.dev/channels/avcopan/automech) channel on prefix.dev, which also has autogeom:

```bash
pixi workspace channel add https://repo.prefix.dev/avcopan/automech
pixi add autostorage
```

Or install it from PyPI:

```bash
pip install autostorage  # or: uv add autostorage
```

## Usage

```python
import numpy as np
from sqlmodel import select

from autostorage import (
    CalculationGeometryLink,
    CalculationRow,
    Database,
    GeometryRow,
    ModelRow,
    PropertyValueRow,
    Role,
    StationaryPointRow,
    energy_property_kind,
    query,
    rdkit_inchi,
)

# Open (or create) a SQLite database; ":memory:" also works for scratch use.
with Database("workflow.db") as db, db.session() as session:
    # Create a model specifying the program, method, and basis.
    model = ModelRow(program="orca", method="b3lyp", basis="def2-svp")

    # Create a calculation using this model.
    calc = CalculationRow(model=model, calc_type="energy")

    # Create a geometry (validated by autogeom: known elements, consistent spin).
    geo = GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 0.96], [0, 0, 0], [0.93, 0, -0.24]]),
        charge=0,
        spin=0,
    )

    # Link the geometry to the calculation as an input.
    link = CalculationGeometryLink(calculation=calc, geometry=geo, role=Role.INPUT)

    # Add all objects to the session and commit.
    session.add_all([model, calc, geo, link])
    session.commit()

    # Attach an energy to the geometry/calculation pair. Values are validated
    # against their property kind ("energy", "gradient", "hessian") on flush.
    energy = PropertyValueRow(
        geometry=geo,
        calculation=calc,
        property_kind_name=energy_property_kind.name,
        value=-76.02,
    )
    session.add(energy)
    session.commit()

    # Query the energy back by geometry and property kind.
    found = session.exec(
        select(PropertyValueRow).where(
            PropertyValueRow.geometry_id == geo.id,
            PropertyValueRow.property_kind_name == "energy",
        )
    ).one()
    print(float(found.value))

    # Stationary points are automatically given identities (InChI, SMILES,
    # Hill formula), which can be used to look them up.
    session.add(StationaryPointRow(geometry=geo, calculation=calc))
    session.commit()
    stmt = query.stationary_point_by_identity(rdkit_inchi, "InChI=1S/H2O/h1H2")
    print(session.exec(stmt).all())
```

`Database.session()` returns an `AutostorageSession` (a `sqlmodel.Session`, so `session.exec(...)` is available) that supports the context manager protocol. Validation and automatic identities are only applied by these sessions. Sessions don't commit automatically: call `session.commit()` explicitly to persist changes.

For a full worked example covering geometries, trajectories, results, stationary points, stages, and steps, see [`examples/stationary.py`](https://github.com/avcopan/autostorage/blob/main/examples/stationary.py).

See the [documentation](https://avcopan.github.io/autostorage/) for the user guide and API reference.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change. See [Contributing](https://github.com/avcopan/autostorage/blob/main/CONTRIBUTING.md) for the workflow and design rules.

## License

This project is licensed under the [MIT License](https://github.com/avcopan/autostorage/blob/main/LICENSE).

## Credits

This package was created with [copier](https://copier.readthedocs.io/) and the [avcopan/copier-pixi-python](https://github.com/avcopan/copier-pixi-python) project template.
