"""Example demonstrating a 2D scan over both O-H bonds in H2O."""

import numpy as np

from autostorage import Database
from autostorage.models import (
    CalculationGeometryLink,
    CalculationRow,
    CalculationTrajectoryLink,
    GeometryRow,
    GeometryTrajectoryLink,
    ModelRow,
    Role,
    StageRow,
    StageStationaryLink,
    StationaryPointRow,
    StepRow,
    TrajectoryRow,
)

# Create database
db = Database("example_scan.db", echo=True)

with db.session() as session:
    # Create a 2D scan trajectory (varying both O-H bond lengths)
    # ndim=2 for a 2D scan grid
    trajectory = TrajectoryRow(ndim=2)
    session.add(trajectory)
    session.flush()

    # Create scan model (a relaxed scan calculation)
    model = ModelRow(
        calc_type="scan",
        program="psi4",
        method="b3lyp",
        basis="6-31g*",
    )
    session.add(model)
    session.flush()

    # Create the scan calculation
    calc_scan = CalculationRow(model_id=model.id)
    session.add(calc_scan)
    session.flush()

    # Link the calculation to the trajectory it produced
    calc_traj_link = CalculationTrajectoryLink(
        calculation_id=calc_scan.id,
        trajectory_id=trajectory.id,
        role=Role.OUTPUT,
    )
    session.add(calc_traj_link)

    # Generate a simple 3x3 grid of H2O geometries varying both O-H bonds
    # Base geometry: equilibrium-ish H2O
    scan_geometries = []
    r1_values = [0.90, 0.96, 1.02]  # First O-H bond lengths (Angstrom)
    r2_values = [0.90, 0.96, 1.02]  # Second O-H bond lengths (Angstrom)

    for i, r1 in enumerate(r1_values):
        for j, r2 in enumerate(r2_values):
            # Create H2O geometry with varying bond lengths
            # O at origin, H atoms along x and symmetric about xz-plane
            geom = GeometryRow(
                symbols=["O", "H", "H"],
                coordinates=np.array(
                    [
                        [0.0, 0.0, 0.0],
                        [
                            r1 * np.cos(np.radians(52)),
                            r1 * np.sin(np.radians(52)),
                            0.0,
                        ],
                        [
                            r2 * np.cos(np.radians(52)),
                            -r2 * np.sin(np.radians(52)),
                            0.0,
                        ],
                    ]
                ),
                charge=0,
                spin=0,
            )
            session.add(geom)
            scan_geometries.append((geom, (i, j)))

    session.flush()

    # Link each geometry to the trajectory with its scan index
    for geom, (i, j) in scan_geometries:
        geom_traj_link = GeometryTrajectoryLink(
            geometry_id=geom.id,
            trajectory_id=trajectory.id,
            index=(i, j),  # 2D index in the scan grid
        )
        session.add(geom_traj_link)

        # Also link each geometry as an output of the scan calculation
        geom_calc_link = CalculationGeometryLink(
            geometry_id=geom.id,
            calculation_id=calc_scan.id,
            role=Role.OUTPUT,
        )
        session.add(geom_calc_link)

    session.flush()

    # Create pseudo stationary points for the scan endpoints and a TS
    # Start point: shortest bonds (0, 0)
    stat_start = StationaryPointRow(
        geometry_id=scan_geometries[0][0].id,  # (0, 0)
        calculation_id=calc_scan.id,
        order=0,
        is_pseudo=True,
        is_valid=False,
    )

    # End point: longest bonds (2, 2)
    stat_end = StationaryPointRow(
        geometry_id=scan_geometries[-1][0].id,  # (2, 2)
        calculation_id=calc_scan.id,
        order=0,
        is_pseudo=True,
        is_valid=False,
    )

    # Pseudo TS: center of the scan grid (1, 1)
    middle_geom = next(g for g, idx in scan_geometries if idx == (1, 1))
    stat_ts = StationaryPointRow(
        geometry_id=middle_geom.id,
        calculation_id=calc_scan.id,
        order=1,
        is_pseudo=True,
        is_valid=False,
    )

    session.add_all([stat_start, stat_end, stat_ts])
    session.flush()

    # Create stages for the start, end, and TS points
    stage_start = StageRow(is_ts=False)
    stage_end = StageRow(is_ts=False)
    stage_ts = StageRow(is_ts=True)
    session.add_all([stage_start, stage_end, stage_ts])
    session.flush()

    # Link stationary points to stages
    session.add_all(
        [
            StageStationaryLink(stationary_id=stat_start.id, stage_id=stage_start.id),
            StageStationaryLink(stationary_id=stat_end.id, stage_id=stage_end.id),
            StageStationaryLink(stationary_id=stat_ts.id, stage_id=stage_ts.id),
        ]
    )
    session.flush()

    # Create a step connecting start and end through the pseudo TS
    step = StepRow(
        stage_id1=min(stage_start.id, stage_end.id),
        stage_id2=max(stage_start.id, stage_end.id),
        stage_id_ts=stage_ts.id,
        is_barrierless=False,
    )
    session.add(step)

    # Commit all changes
    session.commit()
