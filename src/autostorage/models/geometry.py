"""Geometry models."""

from typing import TYPE_CHECKING

import numpy as np
import pint
from automol import Geometry
from automol.types import FloatArray
from pydantic import ConfigDict
from qcdata import Structure
from sqlalchemy.types import JSON, String
from sqlmodel import Column, Field, Relationship, SQLModel

from ..types import FloatArrayTypeDecorator, RowID
from .links import CalculationGeometryLink
from .optional import PartialMixin

if TYPE_CHECKING:
    from .data import EnergyRow
    from .stationary import StationaryPointRow


class GeometryRow(PartialMixin, Geometry, SQLModel, table=True):
    """
    Molecular geometry definition and metadata.

    Attributes
    ----------
    symbols
        List of atomic symbols in order.
    coordinates
        Atomic coordinates in Angstrom.
    charge
        Total molecular charge.
    spin
        Number of unpaired electrons (2S).
    hash
        Unique hash of the geometry for indexing.

    SQLModel Relationships
    -------------------------
    calculation_links
        List of linked CalculationGeometryLinks allowing access to Role directly.
    energies
        List of calculated energies for this geometry.
    stationary_point
        StationaryPointRow associated with this geometry.

    Methods
    -------
    to_qc_structure
        Convert GeometryRow to a qc Structure object.
    from_qc_structure
        (Static) Create a GeometryRow from a qc Structure object.
    """

    # - SQL Metadata ------------------
    __tablename__ = "geometry"
    model_config = ConfigDict(arbitrary_types_allowed=True)
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    # - Attributes --------------------
    symbols: list[str] = Field(sa_column=Column(JSON))
    coordinates: FloatArray = Field(sa_column=Column(FloatArrayTypeDecorator))
    charge: int = Field(default=0)
    spin: int = Field(default=0)
    hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), index=True, nullable=True, unique=True),
    )
    # ^ Populated by event listener
    # - SQLModel relationships --------
    calculation_links: list[CalculationGeometryLink] = Relationship(
        back_populates="geometry"
    )
    energies: list["EnergyRow"] = Relationship(
        back_populates="geometry", cascade_delete=True
    )
    stationary_point: "StationaryPointRow" = Relationship(back_populates="geometry")

    # - Methods -----------------------
    @staticmethod
    def from_geometry(geo: Geometry) -> "GeometryRow":
        """
        Instantiate GeometryRow from Geometry.

        Returns
        -------
        GeometryRow
        """
        return GeometryRow(**geo.model_dump())

    def geometry(self) -> Geometry:
        """
        Instantiate Geometry from GeometryRow.

        Returns
        -------
        Geometry
        """
        return Geometry(**self.model_dump())

    @staticmethod
    def from_structure(*, struc: Structure) -> "GeometryRow":
        """
        Instantiate GeometryRow from qcdata Structure.

        Parameters
        ----------
        struc
            The qcdata Structure to convert.

        Returns
        -------
        GeometryRow
            GeometryRow in Angstrom.
        """
        return GeometryRow(
            symbols=struc.symbols,
            coordinates=struc.geometry * pint.Quantity("bohr").m_as("angstrom"),
            charge=struc.charge,
            spin=struc.multiplicity - 1,
        )

    def structure(self) -> Structure:
        """
        Instantiate qcdata Structure from GeometryRow.

        Returns
        -------
        Structure
            qcdata Structure in Bohr.
        """
        return Structure(
            symbols=self.symbols,
            geometry=np.array(self.coordinates)
            * pint.Quantity("angstrom").m_as("bohr"),
            charge=self.charge,
            multiplicity=self.spin + 1,
        )
