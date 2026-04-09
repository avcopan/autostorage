"""Calculation row model and associated models and functions."""

from pathlib import Path

from automol import Geometry, geom
from automol.types import FloatArray
from pydantic import ConfigDict
from sqlalchemy import event
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship, Session, SQLModel, select

from .calcn import Calculation, calculation_hash, hash_registry
from .types import FloatArrayTypeDecorator, PathTypeDecorator, Role, RowID


# --- Link Models -------------------------------
class StationaryIdentityLink(SQLModel, table=True):
    """
    Stationary point to identity link row.

    Parameters
    ----------
    stationary_id
        Foreign key to the associated molecular structure; part of the
        composite primary key.
    identity_id
        Foreign key to the calculation producing the stationary point; part of
        the composite primary key.
    """

    __tablename__ = "stationary_identity_link"

    stationary_id: RowID = Field(foreign_key="stationary_point.id", primary_key=True)
    identity_id: RowID = Field(foreign_key="identity.id", primary_key=True)


class CalculationGeometryLink(SQLModel, table=True):
    """
    Calculation to geometry link row.

    Parameters
    ----------
    geometry_id
        Foreign key to the associated geometry; part of the
        composite primary key.
    calculation_id
        Foreign key to the associated calculation; part of
        the composite primary key.
    role
        Role of the geometry in the calculation (e.g. "input", "output")
    """

    __tablename__ = "calculation_geometry_link"
    model_config = ConfigDict(use_enum_values=True)

    geometry_id: RowID = Field(foreign_key="geometry.id", primary_key=True)
    calculation_id: RowID = Field(foreign_key="calculation.id", primary_key=True)
    role: Role


# --- Calculation Models ------------------------
class CalculationRow(Calculation, SQLModel, table=True):
    """
    Calculation metadata table row.

    Parameters
    ----------
    input_geometry_id
        GeometryRow ID corresponding to input Geometry
    output_geometry_id
        GeometryRow ID corresponding to output Geometry
    program
        The quantum chemistry program used (e.g., "Psi4", "Gaussian").
    superprogram
        The geometry optimizer program used (e.g., "geomeTRIC"), if applicable.
    method
        Computational method (e.g., "B3LYP", "MP2").
    basis
        Basis set, if applicable.
    input
        Input file for the calculation, if applicable.
    keywords
        QCIO keywords for the calculation.
    superprogram_keywords
        Geometry optimizer keywords for the calculation.
    cmdline_args
        Command line arguments for the calculation.
    files
        Additional files required for the calculation.
    calctype
        Type of calculation (e.g., "energy", "gradient", "hessian").
    program_version
        Version of the quantum chemistry program.
    superprogram_version
        Version of the geometry optimizer program.
    scratch_dir
        Working directory.
    wall_time
        Wall time.
    hostname
        Name of host machine.
    hostcpus
        Number of CPUs on host machine.
    hostmem
        Amount of memory on host machine.
    extras
        Additional metadata.

    Linked Tables
    -------------
    energies
        Corresponding EnergyRow(s).
    hashes
        Corresponding CalculationHashRow(s).
    stationary_points
        Corresponding StationaryPointRow(s).
    """

    __tablename__ = "calculation"

    id: RowID | None = Field(default=None, primary_key=True)

    # Have to redeclare these fields for sql type verification.
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
    extras: dict[str, str | dict | None] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    scratch_dir: Path | None = Field(default=None, sa_column=Column(PathTypeDecorator))

    geometries: list["GeometryRow"] = Relationship(
        back_populates="calculations", link_model=CalculationGeometryLink
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    hashes: list["CalculationHashRow"] = Relationship(
        back_populates="calculation", cascade_delete=True
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="calculation"
    )


class CalculationHashRow(SQLModel, table=True):
    """
    Hash value for a calculation.

    One row corresponds to one hash type applied to one calculation.

    Parameters
    ----------
    id: int
        CalculationHashRow id.
    calculation_id: int
        CalculationRow id.
    name: str
        Type of CalculationRow hash (e.g., "minimal" or "full")
    value: str
        Value of CalculationRow hash.

    Linked Tables
    -------------
    calculation
        Corresponding CalculationRow.
    """

    __tablename__ = "calculation_hash"

    id: RowID | None = Field(default=None, primary_key=True)
    calculation_id: RowID = Field(
        foreign_key="calculation.id", index=True, nullable=False, ondelete="CASCADE"
    )

    name: str = Field(index=True)
    value: str = Field(sa_column=Column(String(64), index=True, nullable=False))

    calculation: CalculationRow = Relationship(back_populates="hashes")


@event.listens_for(Session, "after_flush")
def populate_calculation_hashes(session, flush_context) -> None:  # noqa: ANN001, ARG001
    """Populate the 'minimal' hash for newly added CalculationRow objects."""
    available = set(hash_registry.available())

    for row in session.new:
        if not isinstance(row, CalculationRow):
            continue

        existing = {h.name for h in row.hashes}
        missing = available - existing
        if not missing:
            continue

        calc = row

        for name in missing:
            value = calculation_hash(calc, name=name)

            session.add(
                CalculationHashRow(
                    calculation_id=row.id,
                    name=name,
                    value=value,
                )
            )


# --- Geometry Models ---------------------------
class GeometryRow(Geometry, SQLModel, table=True):
    """
    Molecular geometry table row.

    Parameters
    ----------
    id
        Primary key.
    symbols
        Atomic symbols in order (e.g., ``["H", "O", "H"]``).
        The length of ``symbols`` must match the number of atoms.
    coordinates
        Cartesian coordinates of the atoms in Angstroms.
        Shape is ``(len(symbols), 3)`` and the ordering corresponds to ``symbols``.
    charge
        Total molecular charge.
    spin
        Number of unpaired electrons, i.e. two times the spin quantum number (``2S``).
    hash
        Optional hash of the geometry for quick comparisons.
    energy
        Relationship to the associated energy record, if present.

    Linked Tables
    -------------
    energies
        Corresponding EnergyRow(s).
    stationary_point
        Corresponding StationaryPointRow.
    """

    __tablename__ = "geometry"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: RowID | None = Field(default=None, primary_key=True)

    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))
    hash: str | None = Field(
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
        default=None,
    )
    # ^ Populated by event listener below

    calculations: list["CalculationRow"] = Relationship(
        back_populates="geometries", link_model=CalculationGeometryLink
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="geometry", cascade_delete=True
    )
    stationary_point: "StationaryPointRow" = Relationship(back_populates="geometry")

    # Validate coordinates shape with a field validator:
    #    @field_validator("coordinates")
    #    @classmethod
    #    def validate_shape(cls, v):
    #        if not all(len(row) == 3 for row in v):
    #            raise ValueError("Coordinates must be shape (N, 3)")  # noqa: ERA001
    #        return v  # noqa: ERA001

    # Add formula field for indexing:
    #    formula: str = Field(sa_column=Column(String, nullable=False, index=True))  # noqa: E501, ERA001

    # Define symbols -> formula conversion function:
    #    def formula_from_symbols(symbols: list[str]) -> str

    # Attach SQLAlchemy event listener to auto-set formula on insert:
    #     from sqlalchemy import event  # noqa: ERA001
    #     @event.listens_for(GeometryRow, "before_insert")
    #     @event.listens_for(GeometryRow, "before_update")
    #     def populate_formula(mapper, connection, target: GeometryRow):
    #         target.formula = formula_from_symbols(target.symbols)  # noqa: ERA001
    # This will implement the symbol-formula sync at the ORM level, so that they
    # automatically stay in sync with any inserts or updates.


# --- Data Models -------------------------------
class EnergyRow(SQLModel, table=True):
    """
    Energy table row.

    Parameters
    ----------
    id
        Primary key.
    geometry_id
        Foreign key referencing the geometry table; part of the composite primary key.
    calculation_id
        Foreign key referencing the calculation table; part of the composite
        primary key.
    value
        Energy in Hartree.

    Linked Tables
    -------------
    geometry
        Corresponding GeometryRow.
    calculation
        Corresponding CalculationRow.
    """

    __tablename__ = "energy"

    id: RowID | None = Field(default=None, primary_key=True)

    geometry_id: RowID | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE"
    )
    calculation_id: RowID | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE"
    )

    value: float

    calculation: CalculationRow = Relationship(back_populates="energies")
    geometry: GeometryRow = Relationship(back_populates="energies")


# --- Stationary Models -------------------------
class StationaryPointRow(SQLModel, table=True):
    """
    Stationary point table row.

    Stores information about optimized geometries.

    Parameters
    ----------
    id
        Primary key.
    geometry_id
        Foreign key to the associated molecular geometry.
    calculation_id
        Foreign key to the calculation producing the stationary point.
    order
        Order of the stationary point (e.g., minimum = 0, transition = 1)

    Linked Tables
    -------------
    geometry
        Corresponding GeometryRow.
    calculation
        Corresponding CalculationRow.
    identities
        Corresponding IdentityRow(s).
    """

    __tablename__ = "stationary_point"

    id: RowID | None = Field(default=None, primary_key=True)

    geometry_id: RowID = Field(foreign_key="geometry.id")
    calculation_id: RowID = Field(foreign_key="calculation.id")

    order: int | None = Field(default=-1)

    geometry: "GeometryRow" = Relationship(back_populates="stationary_point")
    calculation: "CalculationRow" = Relationship(back_populates="stationary_points")

    identities: list["IdentityRow"] = Relationship(
        back_populates="stationary_points", link_model=StationaryIdentityLink
    )

    metrics: list["MetricRow"] = Relationship(
        back_populates="stationary_point",
    )


class IdentityRow(SQLModel, table=True):
    """
    Stationary point identity row.

    Parameters
    ----------
    id
        Primary key.
    type
        The category this identity falls within (e.g., "stereoisomer").
    algorithm
        Method used to determine this identity (e.g., "InChI").
    value
        Value produced by the identity algorithm.

    Linked Tables
    -------------
    stationary_points
        Corresponding StationaryPointRow(s).
    """

    __tablename__ = "identity"

    id: RowID | None = Field(default=None, primary_key=True)

    type: str
    algorithm: str
    value: str

    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="identities", link_model=StationaryIdentityLink
    )


class MetricRow(SQLModel, table=True):
    """
    Storage for conformer comparison metrics (e.g., inertia tensor RMSD).

    Parameters
    ----------
    id
        Primary key.
    stationary_id
        Foreign key to the analyzed geometry.
    reference_id
        Foreign key to the reference geometry.
    type
        The category this metric falls within (e.g., "conformer").
    algorithm
        Method used to determine this metric (e.g., "moi rmsd").
    value
        Value produced by the metric algorithm.

    Linked Tables
    -------------
    stationary_point
        Corresponding StationaryPointRow.
    """

    __tablename__ = "metric"

    id: RowID | None = Field(default=None, primary_key=True)

    stationary_id: RowID = Field(foreign_key="stationary_point.id", index=True)

    type: str = Field(index=True)
    label: str
    value: float

    stationary_point: "StationaryPointRow" = Relationship(back_populates="metrics")


# --- Listeners ---------------------------------
@event.listens_for(StationaryPointRow, "after_insert")
def stationary_post_processing(mapper, connection, target: StationaryPointRow) -> None:  # noqa: ANN001, ARG001
    """Automatically tags InChI and default metrics after inserting StationaryPoint."""
    session = Session(bind=connection)

    if target.id is None:
        msg = f"{target = } not assigned an id."
        raise LookupError(msg)

    try:
        # NOTE: If target.geometry isn't loaded, we need to fetch it
        geom_stmt = select(GeometryRow).where(GeometryRow.id == target.geometry_id)
        geom_row = session.exec(geom_stmt).first()

        if not geom_row:
            msg = (
                f"{target.geometry_id} does not correspond to an entry in the database."
            )
            raise LookupError(msg)  # noqa: TRY301

        inchi_string = geom.inchi(geom_row)

        inchi_stmt = select(IdentityRow).where(
            IdentityRow.algorithm == "InChI", IdentityRow.value == inchi_string
        )
        id_row = session.exec(inchi_stmt).first()

        if id_row is None:
            id_row = IdentityRow(
                type="stereoisomer",
                algorithm="InChI",
                value=inchi_string,
            )
            session.add(id_row)
            session.flush()

        if id_row.id is None:
            msg = f"{id_row = } not assigned an id."
            raise LookupError(msg)  # noqa: TRY301

        link = StationaryIdentityLink(stationary_id=target.id, identity_id=id_row.id)
        session.add(link)

        session.commit()

    except Exception as e:
        session.rollback()
        msg = f"Failed to generate InChI {target.id}"
        raise RuntimeError(msg) from e


@event.listens_for(GeometryRow, "before_insert")
def populate_geometry_hash(mapper, connection, target: GeometryRow) -> None:  # noqa: ANN001, ARG001
    """Populate GeometryRow hash before inserts and updates."""
    if target.hash is None:
        target.hash = geom.geometry_hash(target)
