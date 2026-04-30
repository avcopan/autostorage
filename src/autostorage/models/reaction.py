"""Reaction models."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from ..types import RowID
from .links import StationaryStageLink
from .optional import PartialMixin

if TYPE_CHECKING:
    from .stationary import StationaryPointRow


class StageRow(PartialMixin, SQLModel, table=True):
    """
    A specific chemical state (reactant, product, or TS) in a reaction.

    Attributes
    ----------
    is_ts
        Whether this stage represents a transition state.

    SQLModel Relationships
    ----------------------
    steps_1, steps_2
        Connection to StepRows where this stage is a reactant or product.
    steps_ts
        Connection to StepRows where this stage is the transition state.
    Linked Rows
    -----------
    stationary_points
        Geometries mapped to this reaction stage.
    """

    # - SQL Metadata ------------------
    __tablename__ = "stage"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    # - Attributes --------------------
    is_ts: bool = Field(description="Stage represents transition state.")
    # - SQLModel relationships --------
    steps_1: list["StepRow"] = Relationship(
        back_populates="stage1",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id1]"},
    )
    steps_2: list["StepRow"] = Relationship(
        back_populates="stage2",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id2]"},
    )
    steps_ts: list["StepRow"] = Relationship(
        back_populates="stage_ts",
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id_ts]"},
    )
    stationary_points: list["StationaryPointRow"] = Relationship(
        back_populates="stages", link_model=StationaryStageLink
    )


# --- Stage Models ------------------------------
class StepRow(PartialMixin, SQLModel, table=True):
    """
    An elementary reaction step connecting multiple stages.

    Attributes
    ----------
    stage_id1
        Foreign key to the first reactant/product stage.
    stage_id2
        Foreign key to the second reactant/product stage.
    stage_id_ts
        Foreign key to the transition state stage.
    is_barrierless
        Flag for reactions without a formal transition state.

    SQLModel Relationships
    ----------------------
    stage1, stage2, stage_ts
        The specific StageRows linked by this step.
    """

    # - SQL Metadata ------------------
    __tablename__ = "step"
    # - Row id ------------------------
    id: RowID | None = Field(default=None, primary_key=True)
    # - Foreign keys ------------------
    stage_id1: RowID = Field(
        foreign_key="stage.id",
        index=True,
        description="Foreign key to the 1st reaction stage.",
    )
    stage_id2: RowID = Field(
        foreign_key="stage.id",
        index=True,
        description="Foreign key to the 2nd reaction stage.",
    )
    stage_id_ts: RowID = Field(
        foreign_key="stage.id",
        index=True,
        description="Foreign key to the TS reaction stage.",
    )
    # - Attributes --------------------
    is_barrierless: bool = Field(
        description="Reaction step does not involve a TS stage."
    )
    # - SQLModel relationships --------
    stage1: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id1]"}
    )
    stage2: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id2]"}
    )
    stage_ts: "StageRow" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[StepRow.stage_id_ts]"}
    )
