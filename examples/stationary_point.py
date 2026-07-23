"""End-to-end example of the non-reaction parts of the autostorage data model.

Builds a synthetic water (H2O) optimization + frequency workflow entirely from literal
coordinates (no external file I/O), touching every row model except `StageRow`/`StepRow`
and their reaction-specific link tables.

Run with::

    pixi run -e dev python examples/stationary_point.py
"""

import numpy as np
from automol import Algorithm
from numpy.random import Generator

from autostorage import (
    CalcType,
    CalculationGeometryLink,
    CalculationRow,
    Database,
    EnergyRow,
    GeometryRow,
    GradientRow,
    HessianRow,
    IdentityRow,
    ModelRow,
    Role,
    StationaryPointRow,
    TrajectoryRow,
    ValidationRow,
)
from autostorage.models import (
    CalculationTrajectoryLink,
    StationaryIdentityLink,
    TrajectoryGeometryLink,
)


def optimize_water(
    db: Database, model: ModelRow
) -> tuple[CalculationRow, GeometryRow, GeometryRow]:
    """Run a synthetic optimization, linking an input geometry to its output."""
    opt_calc = CalculationRow(model=model, calc_type=CalcType.OPT)
    input_geo = GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 0.9], [0, 0, 0], [0.85, 0.1, 0]]),
        charge=0,
        spin=0,
    )
    optimized_geo = GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 0.8], [0, 0, 0], [0.8, 0, 0]]),
        charge=0,
        spin=0,
    )
    db.add_all(
        [
            opt_calc,
            input_geo,
            optimized_geo,
            CalculationGeometryLink.create(opt_calc, input_geo, role=Role.INPUT),
            CalculationGeometryLink.create(opt_calc, optimized_geo, role=Role.OUTPUT),
        ]
    )
    db.commit()
    print(
        f"optimization calculation {opt_calc.id}: "
        f"{len(opt_calc.input_geometries)} input, "
        f"{len(opt_calc.output_geometries)} output geometry/geometries"
    )
    return opt_calc, input_geo, optimized_geo


def mark_stationary_point(
    db: Database, opt_calc: CalculationRow, optimized_geo: GeometryRow
) -> StationaryPointRow:
    """Record the optimized geometry as a stationary point.

    InChI and conformer identities are attached automatically on commit (see
    `autostorage.events.add_inchi_identities`/`assign_conformer_ids`) -- this
    function doesn't construct those manually, only reads them back.
    """
    stationary = StationaryPointRow(
        calculation=opt_calc, geometry=optimized_geo, order=0
    )
    db.add(stationary)
    db.commit()

    inchi = stationary.identity(kind="stereoisomer")
    conformer = stationary.identity(algorithm=Algorithm.IRMSD)
    assert inchi is not None
    assert conformer is not None
    print(
        f"stationary point {stationary.id} "
        f"(order={stationary.order}, is_valid={stationary.is_valid}):"
    )
    print(f"  auto-attached InChI: {inchi.value}")
    print(f"  auto-attached conformer id: {conformer.value}")
    for extra in inchi.identity_extras:
        print(f"  auto-attached {extra.attribute}: {extra.value}")

    # Algorithms outside `events.AUTO_MANAGED_IDENTITY_ALGORITHMS` (e.g. a
    # human-curated SMILES) have to be attached explicitly.
    smiles = IdentityRow.find_or_create(db, algorithm=Algorithm.RDKIT_SMILES, value="O")
    db.add(StationaryIdentityLink(stationary_id=stationary.id, identity_id=smiles.id))
    db.commit()
    print(f"  manually-attached SMILES: {smiles.value}")

    return stationary


def record_trajectory(
    db: Database,
    opt_calc: CalculationRow,
    input_geo: GeometryRow,
    optimized_geo: GeometryRow,
) -> None:
    """Record a trajectory for the optimization path (input -> optimized)."""
    trajectory = TrajectoryRow()
    db.add(trajectory)
    db.commit()
    db.add_all(
        [
            TrajectoryGeometryLink.create(input_geo, trajectory, index=[0]),
            TrajectoryGeometryLink.create(optimized_geo, trajectory, index=[1]),
            CalculationTrajectoryLink.create(opt_calc, trajectory, role=Role.OUTPUT),
        ]
    )
    db.commit()
    print(
        f"trajectory {trajectory.id} holds {len(trajectory.geometry_links)} geometries"
    )


def run_frequency_calc(
    db: Database,
    model: ModelRow,
    optimized_geo: GeometryRow,
    stationary: StationaryPointRow,
    rng: Generator,
) -> None:
    """Attach a Gradient and Hessian to the optimized geometry.

    `is_valid` on `stationary` is recomputed automatically whenever a Hessian is
    added for its geometry (see `autostorage.events.validate_geometry_orders`),
    reflecting whether the point's declared `order` agrees with the (here,
    randomly generated, so not necessarily consistent) Hessian's order.
    """
    freq_calc = CalculationRow(model=model, calc_type=CalcType.FREQUENCY)
    db.add(freq_calc)
    db.add(CalculationGeometryLink.create(freq_calc, optimized_geo, role=Role.INPUT))
    db.commit()

    n = optimized_geo.atom_count
    gradient = GradientRow(
        calculation=freq_calc, geometry=optimized_geo, value=np.zeros(3 * n)
    )
    hessian = HessianRow(
        calculation=freq_calc,
        geometry=optimized_geo,
        value=rng.uniform(size=(3 * n, 3 * n)),
    )
    db.add_all([gradient, hessian])
    db.commit()
    print(
        f"frequency calculation {freq_calc.id}: "
        f"{len(hessian.harmonic_frequencies)} harmonic frequencies, "
        f"order={hessian.order}"
    )

    found_hessian = HessianRow.query(db, geo=optimized_geo, model=model)
    assert found_hessian is not None
    assert found_hessian.id == hessian.id
    print(f"looked up Hessian {found_hessian.id} by geometry + model")
    print(
        f"stationary point {stationary.id} is_valid is now "
        f"{stationary.is_valid} (declared order={stationary.order}, "
        f"Hessian order={hessian.order})"
    )


def record_transition_point(db: Database, model: ModelRow) -> None:
    """Record a distinct stationary point with order=1.

    `order` (minimum vs. saddle point) is a property of the point itself,
    independent of any reaction step/stage.
    """
    ts_geo = GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 1.0], [0, 0, 0], [1.0, 0.3, 0]]),
        charge=0,
        spin=0,
    )
    ts_calc = CalculationRow(model=model, calc_type=CalcType.OPT_TS)
    db.add_all(
        [
            ts_calc,
            ts_geo,
            CalculationGeometryLink.create(ts_calc, ts_geo, role=Role.OUTPUT),
        ]
    )
    ts_stationary = StationaryPointRow(calculation=ts_calc, geometry=ts_geo, order=1)
    db.add(ts_stationary)
    db.commit()
    print(
        f"transition-point candidate {ts_stationary.id} "
        f"recorded with order={ts_stationary.order}"
    )


def record_energy_and_validation(
    db: Database, model: ModelRow, optimized_geo: GeometryRow
) -> None:
    """Attach a single-point energy, look it up, and add a standalone validation."""
    energy_calc = CalculationRow(model=model, calc_type=CalcType.ENERGY)
    db.add(energy_calc)
    db.add(CalculationGeometryLink.create(energy_calc, optimized_geo, role=Role.INPUT))
    db.commit()

    energy = EnergyRow(calculation=energy_calc, geometry=optimized_geo, value=-76.02)
    db.add(energy)
    db.commit()

    found_energy = EnergyRow.query(db, geo=optimized_geo, model=model)
    assert found_energy is not None
    print(f"energy calculation {energy_calc.id}: E = {found_energy.value} Hartree")

    # A validation record, standing on its own with no reaction step attached.
    validation = ValidationRow(
        calculation=energy_calc,
        method="geometry_check",
        extras={"rmsd_to_input": 0.05},
    )
    db.add(validation)
    db.commit()
    print(f"validation {validation.id} ({validation.method}): {validation.extras}")


def main() -> None:
    """Run the example workflow."""
    rng = np.random.default_rng(seed=0)

    with Database("stationary_points.db") as db:
        model = ModelRow.find_or_create(
            db, program="orca", method="b3lyp", basis="def2-svp"
        )
        opt_calc, input_geo, optimized_geo = optimize_water(db, model)
        stationary = mark_stationary_point(db, opt_calc, optimized_geo)
        record_trajectory(db, opt_calc, input_geo, optimized_geo)
        run_frequency_calc(db, model, optimized_geo, stationary, rng)
        record_transition_point(db, model)
        record_energy_and_validation(db, model, optimized_geo)


if __name__ == "__main__":
    main()
