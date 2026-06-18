"""orca stationary example."""

# %%
import sys
from pathlib import Path

from autostorage import Database
from autostorage.database import (
    CalculationRow,
    EnergyRow,
    GeometryRow,
    GradientRow,
    HessianRow,
    ModelRow,
    StationaryPointRow,
    TrajectoryRow,
)
from autostorage.query import first_match, geometry_match

sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers  # ty:ignore[unresolved-import]

db = Database("example.db")

file_dir = Path.cwd() / "data" / "orca_stationary"

# %%
# Define the calculation model
goat_model = ModelRow(
    program="orca", program_version="6.1.1", method="xtb", calc_type="goat"
)
# Query for existing match
goat_model = first_match(db, goat_model) or goat_model

opt_model = ModelRow(
    program="orca", program_version="6.1.1", method="wb97x-3c", calc_type="opt"
)
opt_model = first_match(db, opt_model) or opt_model

freq_model = ModelRow(
    program="orca",
    program_version="6.1.1",
    method="M062X",
    basis="def2-TZVPP",
    calc_type="opt",
)
freq_model = first_match(db, freq_model) or freq_model

ene_model = ModelRow(
    program="orca",
    program_version="6.1.1",
    method="CCSD(T)-F12/RI",
    basis="cc-pVDZ-F12",
    calc_type="energy",
)
ene_model = first_match(db, ene_model) or ene_model

# %% [markdown]
# # Log the GOAT calculation

# %%
# Read the input geometry
init_geo = GeometryRow.from_xyz_file(file_dir / "init.xyz", charge=0, spin=1)
init_geo = geometry_match(db, init_geo) or init_geo

# Instantiate a CalculationRow
goat_calc = CalculationRow(
    model=goat_model,
    input_geometry=init_geo,
    # Save .inp into input provenance dictionary
    input_provenance={"input file": (file_dir / "goat.inp").read_text()},
)

# Check for existing calculation
goat_calc = first_match(db, goat_calc) or goat_calc

if goat_calc.id is None:
    # Read the minimum energy conformer
    min_geo = GeometryRow.from_xyz_file(
        file_dir / "goat.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    goat_calc.output_geometry = geometry_match(db, min_geo) or min_geo

    # Read the final ensemble as a 0-dim trajectory
    ensemble_traj = TrajectoryRow.from_xyz_file(
        file_dir / "goat.finalensemble.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    goat_calc.output_trajectory = ensemble_traj

    db.add(goat_calc)

# %% [markdown]
# # Log the optimization

# %%
opt_calc = CalculationRow(
    model=opt_model,
    input_geometry=goat_calc.output_geometry,
    input_provenance={"input file": (file_dir / "opt.inp").read_text()},
)

opt_calc = first_match(db, opt_calc) or opt_calc

if opt_calc.id is None:
    opt_geo = GeometryRow.from_xyz_file(
        file_dir / "opt.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    opt_calc.output_geometry = geometry_match(db, opt_geo) or opt_geo

    db.add(opt_calc)

    # Enter the optimized geometry as a stationary point
    opt_stp = StationaryPointRow(
        geometry=opt_geo, calculation=opt_calc, order=0, is_pseudo=False
    )

    db.add(opt_stp)

# %% [markdown]
# # Log the second optimization + frequency

# %%
freq_calc = CalculationRow(
    model=freq_model,
    input_geometry=opt_calc.output_geometry,
    input_provenance={"input file": (file_dir / "freq.inp").read_text()},
)

freq_calc = first_match(db, freq_calc) or freq_calc

if freq_calc.id is None:
    freq_geo = GeometryRow.from_xyz_file(
        file_dir / "freq.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    freq_calc.output_geometry = geometry_match(db, freq_geo) or freq_geo
    freq_calc.output_provenance = {
        "zero point correction": helpers.orca_parse_zpe(
            (file_dir / "freq.log").read_text()
        ),
    }

    db.add(freq_calc)

    freq_grad = GradientRow(
        geometry=freq_geo,
        calculation=freq_calc,
        value=helpers.orca_parse_gradient((file_dir / "freq.engrad").read_text()),
    )
    db.add(freq_grad)

    freq_hess = HessianRow(
        geometry=freq_geo,
        calculation=freq_calc,
        value=helpers.orca_parse_hessian((file_dir / "freq.hess").read_text()),
    )
    db.add(freq_hess)

    # Enter the new optimized stationary point
    freq_stp = StationaryPointRow(
        geometry=freq_geo, calculation=freq_calc, hessian=freq_hess
    )
    db.add(freq_stp)


# %% [markdown]
# # Log the single point energy

# %%
ene_calc = CalculationRow(
    model=ene_model,
    input_geometry=freq_calc.output_geometry,
    input_provenance={"input file": (file_dir / "energy.inp").read_text()},
)

ene_calc = first_match(db, ene_calc) or ene_calc

if ene_calc.id is None:
    ene_res = EnergyRow(
        calculation=ene_calc,
        geometry=freq_calc.output_geometry,
        value=helpers.orca_parse_spe((file_dir / "energy.log").read_text()),
    )

    db.add(ene_res)
