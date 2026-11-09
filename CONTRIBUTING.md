# Contributing to autostorage

Contributions are welcome: bug reports, documentation, and code.
For larger changes, please open an issue first to discuss the idea.

## Setup

1. Install [Pixi](https://pixi.prefix.dev/latest/installation/).
2. Fork and clone the repository.
3. In the clone, install the environments and the Git hooks:
   ```bash
   pixi install --all
   pixi run lefthook install
   ```

The project follows the [copier-pixi-python](https://github.com/avcopan/copier-pixi-python) template, whose README explains the tooling in more detail.

## Workflow

| task | what it does |
|---|---|
| `pixi run test` | Run the tests, including the doctests in `src/` |
| `pixi run test-lowest` | Run the tests with the lowest dependency versions allowed by `pyproject.toml` |
| `pixi run pre-commit` | Run every check that runs on commit: format, lint, types, import contracts, both test runs, and a clean-tree check |
| `pixi run pre-commit-check` | The same, without the tests |
| `pixi run docs-preview` | Build and preview the documentation site |
| `pixi run add <pkg>` | Add a run dependency to `pyproject.toml` |

To run a single test, call pytest in the `test` environment:
```bash
pixi run -e test pytest tests/test_models.py::TestGeometryRow
```

Coverage must stay at or above 80%.
Docstrings use the [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings), with types taken from the annotations rather than repeated in `Args:` and `Returns:`.
Docstring examples run as doctests, so keep them working.

### Developing against a local automol

To test changes to automol before they are released, put the automol repository next to this one and run:
```bash
pixi run local start   # use ../automol
pixi run local stop    # use the released automol
```
The local checkout's version must satisfy the automol bound in `pyproject.toml`.
`pixi run pre-commit` switches back to the released automol, so until the automol changes are released, use `pixi run pre-commit-local`.

## Design

### Rows and domain models

Every SQLModel table class has the `Row` suffix (`GeometryRow`, `CalculationRow`, …), even when there is no domain model of the same name.
Domain models, such as `automol.Geometry`, keep the plain name.
This keeps imports unambiguous: a `GeometryRow` is a database row, and a `Geometry` is an in-memory object.
Where a domain model exists, the row extends it rather than wrapping it: `GeometryRow` subclasses `automol.Geometry`, so automol validates it and its functions accept it directly.

### Conversions and validation come from automol

Each conversion or validation rule for automol's models has exactly one home, in automol.
autostorage stores those models but calls automol for their conversions and validation instead of reimplementing them.
For example, identity algorithms come from `automol.AlgorithmRegistry` and are mirrored by name into `IdentityAlgorithmRow`.
If autostorage needs a conversion that automol lacks, add it to automol.

### Layers

Modules are layered, and a module may only import from the layers below it.
`pixi run imports` enforces this with the contract in `pyproject.toml`:

```
autostorage.database                    (highest)
autostorage.events
autostorage.query | autostorage.property
autostorage.models
autostorage.types                       (lowest)
```
