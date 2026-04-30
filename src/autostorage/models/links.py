"""Linker models."""

from typing import TYPE_CHECKING

from pydantic import ConfigDict
from sqlmodel import Field, Relationship, SQLModel

from ..types import Role, RowID
from .optional import PartialMixin

if TYPE_CHECKING:
    from .calculation import CalculationRow
    from .geometry import GeometryRow


class CalculationGeometryLink(PartialMixin, SQLModel, table=True):
    """
    Link CalculationRows to GeometryRows.

    Attributes
    ----------
    geometry_id
        Foreign key to the linked geometry.
    calculation_id
        Foreign key to the linked geometry.
    role
        Role of the geometry in the calculation.

    SQLModel Relationships
    ----------------------
    calculation
        Corresponding CalculationRow.
    geometry
        Corresponding role GeometryRow.
    """

    # - SQL Metadata ------------------
    __tablename__ = "calculation_geometry_link"
    model_config = ConfigDict(use_enum_values=True)
    # - Row id ------------------------
    # - Foreign keys ------------------
    calculation_id: RowID = Field(
        foreign_key="calculation.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Foreign key to the linked geometry.",
    )
    geometry_id: RowID = Field(
        foreign_key="geometry.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Foreign key to the linked geometry.",
    )
    # - Attributes --------------------
    role: Role = Field(description="Role of the geometry in the calculation.")
    # - SQLModel relationships --------
    calculation: "CalculationRow" = Relationship(back_populates="geometry_links")
    geometry: "GeometryRow" = Relationship(back_populates="calculation_links")


class StationaryIdentityLink(PartialMixin, SQLModel, table=True):
    """
    Link StationaryPointRow to IdentityRow.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    identity_id
        Foreign key to the linked identity.
    """

    # - SQL Metadata ------------------
    __tablename__ = "stationary_identity_link"
    # - Row id ------------------------
    # - Foreign keys ------------------
    stationary_id: RowID = Field(
        foreign_key="stationary_point.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Foreign key to the linked stationary point.",
    )
    identity_id: RowID = Field(
        foreign_key="identity.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Foreign key to the linked identity.",
    )
    # - Attributes --------------------
    # - SQLModel relationships --------


class StationaryStageLink(PartialMixin, SQLModel, table=True):
    """
    Link StationaryPointRows to StageRows.

    Attributes
    ----------
    stationary_id
        Foreign key to the linked stationary point.
    stage_id
        Foreign key to the linked reaction stage.
    """

    # - SQL Metadata ------------------
    __tablename__ = "stationary_stage_link"
    # - Row id ------------------------
    # - Foreign keys ------------------
    stationary_id: RowID = Field(
        foreign_key="stationary_point.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Foreign key to the linked stationary point.",
    )
    stage_id: RowID = Field(
        foreign_key="stage.id",
        primary_key=True,
        ondelete="CASCADE",
        description="Foreign key to the linked reaction stage.",
    )
    # - Attributes --------------------
    # - SQLModel relationships --------
