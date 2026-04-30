"""Data models."""

from pydantic import ConfigDict
from sqlmodel import Field, Relationship, SQLModel

from ..types import RowID
from .calculation import CalculationRow
from .geometry import GeometryRow
from .optional import PartialMixin


class EnergyRow(PartialMixin, SQLModel, table=True):
    """
    Results of an energy calculation for a specific geometry.

    Attributes
    ----------
    geometry_id
        Foreign key to the specific geometry.
    calculation_id
        Foreign key to the calculation that produced this energy.
    value
        Energy value in Hartree.

    SQLModel Relationships
    -----------------------
    geometry
        GeometryRow defining the point's coordinates.
    calculation
        Parent CalculationRow.
    """

    # - SQL Metadata ------------------
    __tablename__ = "energy"
    model_config = ConfigDict(arbitrary_types_allowed=True)
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    geometry_id: RowID | None = Field(
        default=None, foreign_key="geometry.id", ondelete="CASCADE"
    )
    calculation_id: RowID | None = Field(
        default=None, foreign_key="calculation.id", ondelete="CASCADE"
    )
    # - Attributes --------------------
    value: float
    # - SQLModel relationships --------
    calculation: CalculationRow = Relationship(back_populates="energies")
    geometry: GeometryRow = Relationship(back_populates="energies")
