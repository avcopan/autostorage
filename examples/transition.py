"""Example demonstrating reaction network features: stages, steps, and validations."""

import numpy as np

from autostorage import Database
from autostorage.models import (
    CalculationGeometryLink,
    CalculationRow,
    EnergyRow,
    GeometryRow,
    ModelRow,
    Role,
    StageRow,
    StageStationaryLink,
    StationaryPointRow,
    StepRow,
    StepValidationLink,
    ValidationRow,
)

# Create database
db = Database("example_transition.db", echo=True)

with db.session() as session:
    # Reactant: pyramidal NH3 (a minimum, order=0)
    reactant_geom = GeometryRow(
        symbols=["N", "H", "H", "H"],
        coordinates=np.array(
            [
                [0.0, 0.0, 0.3],
                [0.94, 0.0, -0.1],
                [-0.47, 0.814, -0.1],
                [-0.47, -0.814, -0.1],
            ]
        ),
        charge=0,
        spin=0,
    )

    # Transition state: planar NH3, the point of inversion (order=1)
    ts_geom = GeometryRow(
        symbols=["N", "H", "H", "H"],
        coordinates=np.array(
            [
                [0.0, 0.0, 0.0],
                [0.99, 0.0, 0.0],
                [-0.495, 0.857, 0.0],
                [-0.495, -0.857, 0.0],
            ]
        ),
        charge=0,
        spin=0,
    )

    # Product: mirror-image pyramidal NH3 (a minimum, degenerate with the reactant)
    product_geom = GeometryRow(
        symbols=["N", "H", "H", "H"],
        coordinates=np.array(
            [
                [0.0, 0.0, -0.3],
                [0.94, 0.0, -0.1],
                [-0.47, 0.814, -0.1],
                [-0.47, -0.814, -0.1],
            ]
        ),
        charge=0,
        spin=0,
    )
    session.add_all([reactant_geom, ts_geom, product_geom])
    session.flush()

    # Calculation model used to locate all three stationary points.
    model = ModelRow(program="psi4", method="b3lyp", basis="6-31g*")
    session.add(model)
    session.flush()

    calc_reactant = CalculationRow(model_id=model.id, calc_type="opt")
    calc_ts = CalculationRow(model_id=model.id, calc_type="opt")
    calc_product = CalculationRow(model_id=model.id, calc_type="opt")
    session.add_all([calc_reactant, calc_ts, calc_product])
    session.flush()

    # Link each geometry to the optimization that produced it as an output.
    session.add_all(
        [
            CalculationGeometryLink(
                geometry_id=reactant_geom.id,
                calculation_id=calc_reactant.id,
                role=Role.OUTPUT,
            ),
            CalculationGeometryLink(
                geometry_id=ts_geom.id,
                calculation_id=calc_ts.id,
                role=Role.OUTPUT,
            ),
            CalculationGeometryLink(
                geometry_id=product_geom.id,
                calculation_id=calc_product.id,
                role=Role.OUTPUT,
            ),
        ]
    )

    # Energy results for each point (Hartree); the TS sits above both minima.
    energy_reactant = EnergyRow(
        geometry_id=reactant_geom.id, calculation_id=calc_reactant.id, value=-56.19513
    )
    energy_ts = EnergyRow(
        geometry_id=ts_geom.id, calculation_id=calc_ts.id, value=-56.17021
    )
    energy_product = EnergyRow(
        geometry_id=product_geom.id, calculation_id=calc_product.id, value=-56.19513
    )
    session.add_all([energy_reactant, energy_ts, energy_product])

    # Stationary points: reactant/product are minima (order=0), the TS is a
    # first-order saddle point (order=1).
    stat_reactant = StationaryPointRow(
        geometry_id=reactant_geom.id, calculation_id=calc_reactant.id, order=0
    )
    stat_ts = StationaryPointRow(
        geometry_id=ts_geom.id, calculation_id=calc_ts.id, order=1
    )
    stat_product = StationaryPointRow(
        geometry_id=product_geom.id, calculation_id=calc_product.id, order=0
    )
    session.add_all([stat_reactant, stat_ts, stat_product])
    session.flush()

    # `add_inchi_identities_before_flush` already attached an InChI identity to
    # each stationary point during the flush above; reactant and product share
    # the same chemical identity since this inversion is degenerate.
    assert stat_reactant.identities
    assert {i.value for i in stat_reactant.identities} == {
        i.value for i in stat_product.identities
    }

    # Stages: one per stationary point, plus the transition-state stage.
    stage_reactant = StageRow(is_ts=False)
    stage_product = StageRow(is_ts=False)
    stage_ts = StageRow(is_ts=True)
    session.add_all([stage_reactant, stage_product, stage_ts])
    session.flush()

    # Link each stationary point to its stage.
    session.add_all(
        [
            StageStationaryLink(
                stationary_id=stat_reactant.id, stage_id=stage_reactant.id
            ),
            StageStationaryLink(
                stationary_id=stat_product.id, stage_id=stage_product.id
            ),
            StageStationaryLink(stationary_id=stat_ts.id, stage_id=stage_ts.id),
        ]
    )
    session.flush()

    # Elementary step connecting reactant and product through the transition state.
    # StepRow requires stage_id1 < stage_id2.
    step = StepRow(
        stage_id1=min(stage_reactant.id, stage_product.id),
        stage_id2=max(stage_reactant.id, stage_product.id),
        stage_id_ts=stage_ts.id,
        is_barrierless=False,
    )
    session.add(step)
    session.flush()

    # Validate the step with an IRC calculation confirming it connects the
    # reactant and product minima, then link the validation to the step.
    irc_model = ModelRow(program="psi4", method="b3lyp", basis="6-31g*")
    session.add(irc_model)
    session.flush()

    irc_calc = CalculationRow(model_id=irc_model.id, calc_type="irc")
    session.add(irc_calc)
    session.flush()

    # The IRC starts from the TS and descends to the reactant and product minima.
    session.add_all(
        [
            CalculationGeometryLink(
                geometry_id=ts_geom.id, calculation_id=irc_calc.id, role=Role.INPUT
            ),
            CalculationGeometryLink(
                geometry_id=reactant_geom.id,
                calculation_id=irc_calc.id,
                role=Role.OUTPUT,
            ),
            CalculationGeometryLink(
                geometry_id=product_geom.id,
                calculation_id=irc_calc.id,
                role=Role.OUTPUT,
            ),
        ]
    )

    irc_validation = ValidationRow(
        calculation_id=irc_calc.id,
        method="irc",
        extras={"connects": "reactant-product"},
    )
    session.add(irc_validation)
    session.flush()

    session.add(StepValidationLink(step_id=step.id, validation_id=irc_validation.id))

    # Commit all changes
    session.commit()
