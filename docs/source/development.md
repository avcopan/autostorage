# Development

## Setup

```bash
git clone <your fork>
cd autostorage
pixi run init
```

`pixi run init` runs `scripts/setup.sh` (direnv, git init/first commit if needed) and then
installs the [lefthook](https://github.com/evilmartians/lefthook) git hooks that run the
pre-commit pipeline described below. All other tasks in this section assume a Pixi install and
are invoked as `pixi run <task>` (task definitions live in `pixi.toml` under
`[feature.dev.tasks]`).

## Everyday tasks

```{list-table}
:header-rows: 1

* - Task
  - What it runs
* - `pixi run fmt`
  - `ruff format .` — code formatting.
* - `pixi run lint`
  - `ruff check . --fix` — linting, with `select = ["ALL"]` in `pyproject.toml` (a small,
    documented ignore list carves out specific rules).
* - `pixi run types`
  - `ty check` — static type-checking.
* - `pixi run imports`
  - `lint-imports` — enforces the [module layering](data-model.md#module-layering) contract.
* - `pixi run test`
  - `pytest`, with coverage.
* - `pixi run pre-commit`
  - Runs all of the above in order, then checks the working tree is clean.
* - `pixi run cov-view`
  - Opens the HTML coverage report (`htmlcov/index.html`) in `$BROWSER`.
* - `pixi run migrate`
  - Applies Alembic migrations to an existing on-disk database — see [Migrations](migrations.md).
```

A single test:

```bash
pixi run -e dev pytest tests/test_models.py::test_name
```

## Testing conventions

- `testpaths = ["tests", "src"]` in `pyproject.toml` — pytest collects both the `tests/`
  directory and `src/`.
- `--doctest-modules` is always on, so any doctest example (`>>> ...`) in a `src/` docstring is
  collected and executed as a test. Keep them accurate and runnable — a stale example fails the
  suite, not just the docs.
- Coverage runs in branch mode (`[tool.coverage.run] branch = true`) with a hard floor:
  `fail_under = 80` in `[tool.coverage.report]`. `pixi run test` fails if coverage drops below
  that, independent of whether individual tests pass.
- `tests/conftest.py` provides shared fixtures: an in-memory `database` fixture
  (`Database(":memory:")`, closed on teardown), a seeded `rng`, and baseline `model_row`/
  `geometry_row`/`calculation_row`/`calc_geo_link` fixtures used across `test_models.py` and
  `test_database.py`.
- `tests/test_migrations.py` is a smoke test that Alembic's `upgrade head` reproduces exactly
  the schema `SQLModel.metadata.create_all` would build — see
  [Keeping migrations and models in sync](migrations.md#keeping-migrations-and-models-in-sync).

## Pre-commit pipeline

`lefthook.yaml` defines two non-parallel command sequences, run via `pixi run pre-commit` /
`pixi run local-pre-commit`:

1. `fmt` → `lint` → `types` → `imports` → `test` → `git diff --exit-code` (fails if formatting/
   linting left the tree dirty).
2. The `local-pre-commit` variant additionally runs `pixi run local start`/`stop` around the
   same sequence, for workflows that need local services up during tests.

CI (`.github/workflows/test.yml`) runs `pixi run pre-commit` on every push/PR, then `pixi run
test` again separately to publish the coverage report.

## Docs

```bash
pixi run docs-build   # sphinx-build docs/source docs/build
pixi run docs-view     # docs-build, then open docs/build/index.html in $BROWSER
```

`docs-view` requires the `BROWSER` environment variable to point at a browser executable (see
`scripts/view-docs.sh`).

Docs are built with Sphinx + [MyST](https://myst-parser.readthedocs.io/) (Markdown) +
[sphinx-autodoc2](https://sphinx-autodoc2.readthedocs.io/) for the {doc}`API reference
<apidocs/index>`, using the `pydata-sphinx-theme`. Docstrings are written in NumPy style
(`tool.ruff.lint.pydocstyle.convention = "numpy"`) but rendered through a small custom parser
(`docs/source/autodoc2_docstrings_parser.py`) that runs them through
`sphinx.ext.napoleon.docstring.NumpyDocstring` before handing off to MyST — this is what lets
`autodoc2`, which doesn't natively understand NumPy-style sections, render them correctly.
Section headings get anchor links (`myst_heading_anchors = 3` in `conf.py`), which is what the
`#section-name` links throughout this documentation rely on.

`.github/workflows/docs.yml` runs `pixi run docs-build` and deploys `docs/build/` to GitHub
Pages on every push to `main`.

## Release process

Releases are driven by [tbump](https://github.com/your-tools/tbump) (`tbump.toml`), which bumps
the version string in `pyproject.toml`, `pixi.toml`, and `src/autostorage/__init__.py` in one
step, then (via its `before_commit` hooks) regenerates `CHANGELOG.md` with
[keepachangelog](https://keepachangelog.com/) and re-locks `pixi.lock`, and finally tags the
commit `v{new_version}`.

```bash
pixi run version    # print the current version
pixi run release    # tbump — walks through the bump interactively
```

Pushing a `v*.*.*` tag triggers `.github/workflows/release.yml`, which builds both a conda
package (`pixi run build-conda`) and a PyPI package (`pixi run build-pypi`), publishes both
(`publish-conda` to Anaconda.org, `publish-pypi` to PyPI — both need their respective secrets in
CI), and creates a GitHub Release with notes extracted from `CHANGELOG.md`.

## Coding standards

See `CONTRIBUTING.md` for naming conventions (`Row`-suffixed SQLModel classes vs. domain
models) and cross-package conversion ownership rules shared across the `automol`/`autostorage`
suite.
