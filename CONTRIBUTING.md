# Contributing to autostorage

Thank you for your interest in contributing to **autostorage**!
Contributions of all kinds are welcome, including bug reports,
documentation improvements, and new features.

This document outlines the basic development workflow and coding
conventions used in the project.

## Development workflow

To get set up:
1. Install [Pixi](https://pixi.prefix.dev/latest/installation/)
2. Fork the repository
3. Clone the repository and run `pixi run init` inside it
To contribute code, submit pull requests with clear descriptions of the changes.
For larger contributions, create an issue first to propose your idea.

## Coding standards

Coding standards are largely enforced by the pre-commit hooks, which perform
formatting and linting ([Ruff](https://github.com/charliermarsh/ruff)),
import linting ([Lint-Imports](https://import-linter.readthedocs.io/en/stable/)),
static type-checking ([Ty](https://github.com/astral-sh/ty)),
and testing ([PyTest](https://docs.pytest.org/en/latest/))
with code coverage reports [CodeCov](https://docs.codecov.com/docs).

Docstrings follow the
[NumPy docstring standard](https://numpydoc.readthedocs.io/en/latest/format.html#docstring-standard).

## Naming Conventions

This project clearly separates **domain models** (in-memory, scientific objects) from **persistence models** (database-backed SQLModel tables). These two layers serve different purposes and are named accordingly.

### Domain Models (Pydantic)

Domain models represent scientific concepts used directly in computation and analysis.

**Characteristics:**
- Implemented using Pydantic (`BaseModel`)
- Used in-memory
- May include validation, units, helper methods, or NumPy integration
- Independent of database concerns

**Naming rule:**
- Use the clean, concept-level name with **no suffix**

**Example:**
```python
class Geometry(BaseModel):
    ...
```

---

### Persistence Models (SQLModel)

Persistence models represent rows stored in a database table.

**Characteristics:**
- Implemented using SQLModel (`SQLModel, table=True`)
- Used for storage, querying, and relationships
- Optimized for serialization and database compatibility
- Considered part of the infrastructure layer

**Naming rule:**
- All SQLModel table classes **must use the `Row` suffix**
- This applies universally, even if no naming conflict currently exists

**Example:**
```python
class GeometryRow(SQLModel, table=True):
    __tablename__ = "geometry"
    ...
```

---

### Rationale

This convention is intentionally strict and uniform:

- Avoids ambiguity between domain objects and database-backed objects
- Prevents future naming conflicts as the domain layer evolves
- Makes imports self-describing and predictable
- Keeps scientific terminology clean and uncluttered
- Reflects how SQLModel instances are typically used (as rows)

**Good:**
```python
from automol.geom import Geometry
from automol.db import GeometryRow
```

**Avoid:**
```python
from automol.geom import Geometry
from automol.db import Geometry  # ambiguous
```

---

## Domain Ownership & Conversions

To maintain a decoupled suite, we follow a **Domain-Driven Design** approach. Each package in the suite is the owner of its specific objects and is the sole authority on how to translate those objects to/from external standards (like qcio).

### The Core Philosophy
> **"If you own the data, you own the interface."**
>
> Contributors should implement conversion logic within the package that defines the internal model. This prevents packages from needing to know the implementation details of every other tool in the suite.

### Example Ownership
| Package | Owned Object | Responsibility | Key Conversion Methods |
|---------|--------------|----------------|------------------------|
| **AutoMol** | `Geometry` | Coordinates, charge, spin, ... | ```from_geometry()``` ```to_geometry()``` |
| **AutoStore** | `Calculation` | Calculation arguments, metadata, provenance, ... | ```from_calculation()``` ```to_calculation()``` |

### Implementation Guidelines

#### 1. Decoupled Conversions

Conversion logic should be implemented as *standalone functions* rather than methods on the class. This keeps our core Pydantic/SQLModel objects lightweight and prevents external dependencies (like qcio or pint) from being required to instantiate a base model.

#### 2. Using the Shared Interface

When bridging objects between packages, always use the standalone conversion functions. For example, if AutoStore needs to generate a ProgramInput, it calls AutoMol's geometry converter rather than manual dictionary mapping:
```python
# Autostore leverages AutoMol's ownership of Geometry
structure = automol.qc.structure.from_geometry(geo)
```

#### 3. Directory Structure & Abstraction Levels
To keep the core of the packages stable and independent, we follow a **Provider Pattern**. Core objects (like `Geometry` and `Calculation`) must remain "pure"--they should have zero knowledge of sub-packages or external libraries like RDKit, qcio, ...

Instead, the **sub-packages** provide bridges. They "import up" from the core and provide necessary translations.

Dependencies should always flow from the specific (sub-packages) to the general (core models).

* **Incorrect**: Putting `from_rdkit()` inside `geometry.py`. This forces the core to be dependent on RDKit.

* **Correct**: Putting `to_geometry()` inside `src/autopilot/rd/mol.py`.

**Rationale**: This allows the core packages to provide the framework for methods developed in this suite without bias towards specific software. Contributors can add support for new software by adding a new-subfolder without risking conflicts in the core model files or creating overly large core scripts.

---

## Handling Redunancy (Data Model Inheritance)
To reduce redundancy between API models and Database rows while maintaining role separation, we use class inheritance to separate domain fields from database metadata.

| Layer | Purpose | Naming |
|------|--------|--------|
| Domain | In-memory scientific models | `Geometry`, `Reaction`, `Molecule` |
| Persistence | SQLModel database tables | `GeometryRow`, `ReactionRow`, `MoleculeRow` |

If you add a new SQLModel table, always use the `Row` suffix — even if there is no corresponding domain model yet.

### Example
`Calculation` | *autostorage.calcn.core* | **(Domain Model)** | This class defines the data schema. 

```python
# Explicitly declaring that this object is not a database table.
class Calculation(SQLModel, table=False):
    # Input fields:
    program: str
    method: str
    basis: str | None = None
    input: str | None = None
    keywords: dict[str, str | dict | None] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    superprogram_keywords: dict[str, str | dict | None] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    cmdline_args: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )
    files: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    calctype: str | None = None
    program_version: str | None = None
    # Provenance fields:
    superprogram: str | None = None
    superprogram_version: str | None = None
    scratch_dir: Path | None = Field(default=None, sa_column=Column(PathTypeDecorator))
    wall_time: float | None = None
    hostname: str | None = None
    hostcpus: int | None = None
    hostmem: int | None = None
    extras: dict[str, str | dict | None] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
```
`CalculationRow` | *autostorage.models.calculation* | **Persistence Model** | This class inherits from Calculation and sets `table=True`. It adds database-specific fields like `id` and SQLAlchemy `Relationship` definitions.
```python
# CalculationRow inherits attributes from Calculation and is declared as a database table.
class CalculationRow(Calculation, table=True):
    __tablename__ = "calculation"

    id: int | None = Field(default=None, primary_key=True)

    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    hashes: list["CalculationHashRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )
```

#### Notes

1. Adding a field to `Calculation` automatically updates the database schema in `CalculationRow`, ensuring field synchronization.

2. Utility functions should be hinted to accept the base `Calculation` class, allowing them to process live API data and be stored in database rows without modification.

3. Models should only selectinload for directly connected tables--do not have extensive selectinload going multiple layers out
---

## Questions

If you have questions about contributing or design decisions, feel free
to open an issue for discussion.

## Notes
Naming conversions: native_object_to_foreign_object, native_object_from_foreign_object
Imports: instead of "from automol import geom", use "import automol" then "automol.geom..." to avoid naming conflicts
