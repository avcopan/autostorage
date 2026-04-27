"""SQLModel row definitions for autostore.

Layers to avoid circular imports at load time:
    links
  → geometry
  → calculation
  → data
  → stationary
  → reaction
  → listeners
"""

from . import listeners  # 1st registers @event.listens_for  # noqa: F401
from .calculation import CalculationHashRow, CalculationRow, ProvenanceRow
from .data import EnergyRow
from .geometry import GeometryRow
from .links import (
    CalculationGeometryLink,
    StationaryIdentityLink,
    StationaryStageLink,
)
from .reaction import StageRow, StepRow
from .stationary import IdentityRow, MetricRow, StationaryPointRow

__all__ = [
    # links
    "CalculationGeometryLink",
    "StationaryIdentityLink",
    "StationaryStageLink",
    # geometry
    "GeometryRow",
    # calculation
    "CalculationRow",
    "ProvenanceRow",
    "CalculationHashRow",
    # data
    "EnergyRow",
    # stationary
    "StationaryPointRow",
    "IdentityRow",
    "MetricRow",
    # reaction
    "StageRow",
    "StepRow",
]
