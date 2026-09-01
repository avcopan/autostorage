"""Example demonstrating stationary points, stages, and steps."""

import numpy as np

from autostorage import Database
from autostorage.models import (
    CalculationGeometryLink,
    CalculationRow,
    EnergyRow,
    GeometryRow,
    GradientRow,
    HessianRow,
    ModelRow,
    Role,
    StageRow,
    StageStationaryLink,
    StationaryPointRow,
    StepRow,
)

# Create database
db = Database("example_stationary.db", echo=True)

with db.session() as session:
    # Create a simple H2O geometry (reactant)
    geom1 = GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=np.array(
            [
                [0.0, 0.0, 0.0],
                [0.0, 0.757, 0.587],
                [0.0, -0.757, 0.587],
            ]
        ),
        charge=0,
        spin=0,
    )
    session.add(geom1)

    # Create a second geometry (product - slightly different H2O)
    geom2 = GeometryRow(
        symbols=["O", "H", "H"],
        coordinates=np.array(
            [
                [0.0, 0.0, 0.0],
                [0.0, 0.800, 0.600],
                [0.0, -0.800, 0.600],
            ]
        ),
        charge=0,
        spin=0,
    )
    session.add(geom2)
    session.flush()

    # Create a calculation model
    model = ModelRow(
        program="psi4",
        method="b3lyp",
        basis="6-31g*",
    )
    session.add(model)
    session.flush()

    # Create calculations that identified the stationary points
    calc1 = CalculationRow(model_id=model.id, calc_type="OPT")
    calc2 = CalculationRow(model_id=model.id, calc_type="OPT")
    session.add_all([calc1, calc2])
    session.flush()

    # Link each geometry to the optimization that produced it as an output
    link_geom1 = CalculationGeometryLink(
        geometry_id=geom1.id, calculation_id=calc1.id, role=Role.OUTPUT
    )
    link_geom2 = CalculationGeometryLink(
        geometry_id=geom2.id, calculation_id=calc2.id, role=Role.OUTPUT
    )
    session.add_all([link_geom1, link_geom2])

    # Add energy results for both geometries
    energy1 = EnergyRow(
        geometry_id=geom1.id,
        calculation_id=calc1.id,
        value=-76.4268193,  # Hartree
    )
    energy2 = EnergyRow(
        geometry_id=geom2.id,
        calculation_id=calc2.id,
        value=-76.4265821,  # Hartree (slightly higher energy)
    )
    session.add_all([energy1, energy2])

    # Add gradient results (3 atoms x 3 coords = 9 values, flattened)
    gradient1 = GradientRow(
        geometry_id=geom1.id,
        calculation_id=calc1.id,
        value=np.array(
            [
                0.0001,
                -0.0002,
                0.0003,  # O atom gradient
                -0.0001,
                0.0001,
                -0.0002,  # H1 atom gradient
                0.0000,
                0.0001,
                -0.0001,  # H2 atom gradient
            ]
        ),
    )
    gradient2 = GradientRow(
        geometry_id=geom2.id,
        calculation_id=calc2.id,
        value=np.array(
            [
                0.0002,
                -0.0003,
                0.0001,
                -0.0002,
                0.0002,
                -0.0001,
                0.0001,
                0.0001,
                0.0000,
            ]
        ),
    )
    session.add_all([gradient1, gradient2])

    # Add hessian results (9x9 matrix for 3 atoms)
    # Create a simple symmetric positive-definite hessian
    hess1_matrix = np.random.RandomState(42).randn(9, 9) * 0.1
    hess1_matrix = (hess1_matrix + hess1_matrix.T) / 2  # Make symmetric
    hess1_matrix += np.eye(9) * 2  # Make positive-definite

    hess2_matrix = np.random.RandomState(43).randn(9, 9) * 0.1
    hess2_matrix = (hess2_matrix + hess2_matrix.T) / 2
    hess2_matrix += np.eye(9) * 2

    hessian1 = HessianRow(
        geometry_id=geom1.id,
        calculation_id=calc1.id,
        value=hess1_matrix.astype(np.float32),
    )
    hessian2 = HessianRow(
        geometry_id=geom2.id,
        calculation_id=calc2.id,
        value=hess2_matrix.astype(np.float32),
    )
    session.add_all([hessian1, hessian2])
    session.flush()

    # Create stationary points (both are minima: order=0)
    stat1 = StationaryPointRow(
        geometry_id=geom1.id,
        calculation_id=calc1.id,
        order=0,
        is_pseudo=False,
        is_validated=True,
    )
    stat2 = StationaryPointRow(
        geometry_id=geom2.id,
        calculation_id=calc2.id,
        order=0,
        is_pseudo=False,
        is_validated=True,
    )
    session.add_all([stat1, stat2])
    session.flush()

    # Create stages (both are non-TS stages)
    stage1 = StageRow(is_ts=False)
    stage2 = StageRow(is_ts=False)
    session.add_all([stage1, stage2])
    session.flush()

    # Link stationary points to stages
    link1 = StageStationaryLink(stationary_id=stat1.id, stage_id=stage1.id)
    link2 = StageStationaryLink(stationary_id=stat2.id, stage_id=stage2.id)
    session.add_all([link1, link2])
    session.flush()

    # Create a barrierless step connecting the two stages
    # StepRow requires stage_id1 < stage_id2
    step = StepRow(
        stage_id1=min(stage1.id, stage2.id),
        stage_id2=max(stage1.id, stage2.id),
        stage_id_ts=None,  # No transition state (barrierless)
        is_barrierless=True,
    )
    session.add(step)

    # Commit all changes
    session.commit()
