# autostorage

A [SQLModel](https://sqlmodel.tiangolo.com/)/SQLAlchemy persistence layer for computational
chemistry workflow data, built on top of [`automol`](https://github.com/avcopan/automol). It
stores molecular geometries, chemical identities, trajectories, stationary points, calculation
results (energies, gradients, Hessians), and the calculations/reaction steps that connect them,
as a graph of related rows in a SQLite database.

Row models extend `automol`'s core data models directly rather than wrapping them —
`GeometryRow` extends `automol.Geometry`, `IdentityRow` extends `automol.Identity` — so any
data already expressed in `automol` types can be persisted with no conversion step.

:::{toctree}
:maxdepth: 2
:caption: Contents

quickstart
data-model
database
events
migrations
development
apidocs/index
:::
