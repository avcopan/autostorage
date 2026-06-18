"""orca transition example."""

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
    StageRow,
    StationaryPointRow,
    StepRow,
    TrajectoryRow,
    ValidationRow,
)
from autostorage.query import first_match, geometry_match, one_match

sys.path.insert(0, str(Path(__file__).resolve().parent))

import helpers  # ty:ignore[unresolved-import]

db = Database("example.db")

file_dir = Path.cwd() / "data" / "orca_transition"

# %% Calculation model
# Define the calculation model
optts_model = ModelRow(
    program="orca",
    program_version="6.1.1",
    method="M062X",
    basis="def2-TZVPP",
    calc_type="optts",
)
# Query for existing match
optts_model = first_match(db, optts_model) or optts_model

ene_model = ModelRow(
    program="orca",
    program_version="6.1.1",
    method="CCSD(T)-F12/RI",
    basis="cc-pVDZ-F12",
    calc_type="energy",
)
ene_model = first_match(db, ene_model) or ene_model

# %%
# Read the input geometry
init_geo = GeometryRow.from_xyz_file(file_dir / "guess.xyz", charge=0, spin=1)
init_geo = geometry_match(db, init_geo) or init_geo

# Instantiate a CalculationRow
optts_calc = CalculationRow(
    model=optts_model,
    input_geometry=init_geo,
    # Save .inp into input provenance dictionary
    input_provenance={"input file": (file_dir / "freq.inp").read_text()},
)

# Check for existing calculation
optts_calc = first_match(db, optts_calc) or optts_calc

if optts_calc.id is None:
    # Read the optimized transition state geometry
    freq_geo = GeometryRow.from_xyz_file(
        file_dir / "freq.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    optts_calc.output_geometry = geometry_match(db, freq_geo) or freq_geo

    optts_calc.output_provenance = {
        "zero point correction": helpers.orca_parse_zpe(
            (file_dir / "freq.log").read_text()
        )
    }
    db.add(optts_calc)

    freq_grad = GradientRow(
        geometry=freq_geo,
        calculation=optts_calc,
        value=helpers.orca_parse_gradient((file_dir / "freq.engrad").read_text()),
    )
    db.add(freq_grad)

    freq_hess = HessianRow(
        geometry=freq_geo,
        calculation=optts_calc,
        value=helpers.orca_parse_hessian((file_dir / "freq.hess").read_text()),
    )
    db.add(freq_hess)

    freq_stp = StationaryPointRow(
        geometry=freq_geo, calculation=optts_calc, order=1, hessian=freq_hess
    )
    db.add(freq_stp)

# %%


ene_calc = CalculationRow(
    model=ene_model,
    input_geometry=optts_calc.output_geometry,
    input_provenance={"input file": (file_dir / "energy.inp").read_text()},
)

ene_calc = first_match(db, ene_calc) or ene_calc

if ene_calc.id is None:
    ene_res = EnergyRow(
        calculation=ene_calc,
        geometry=optts_calc.output_geometry,
        value=helpers.orca_parse_spe((file_dir / "energy.log").read_text()),
    )

    db.add(ene_res)

# %%
irc_model = ModelRow(
    program="orca",
    program_version="6.1.1",
    method="M062X",
    basis="def2-TZVPP",
    calc_type="irc",
)
irc_model = first_match(db, irc_model) or irc_model

irc_calc = CalculationRow(
    model=irc_model,
    input_geometry=optts_calc.output_geometry,
    input_provenance={"input file": (file_dir / "irc.inp").read_text()},
)
irc_calc = first_match(db, irc_calc) or irc_calc

if irc_calc.id is None:
    irc_f_geo = GeometryRow.from_xyz_file(
        file_dir / "irc_IRC_F.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    irc_f_geo = geometry_match(db, irc_f_geo) or irc_f_geo

    irc_b_geo = GeometryRow.from_xyz_file(
        file_dir / "irc_IRC_B.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    irc_b_geo = geometry_match(db, irc_b_geo) or irc_b_geo

    irc_calc.output_trajectory = TrajectoryRow.from_geometries(
        [irc_b_geo, optts_calc.output_geometry, irc_f_geo], indices=[0, 1, 2]
    )

    db.add(irc_calc)

    irc_f_stp = StationaryPointRow(geometry=irc_f_geo, calculation=irc_calc)
    db.add(irc_f_stp)

    irc_b_stp = StationaryPointRow(geometry=irc_b_geo, calculation=irc_calc)
    db.add(irc_b_stp)

    stage_f = StageRow(stationary_points=[irc_f_stp])
    stage_f = first_match(db, stage_f) or stage_f

    stage_b = StageRow(stationary_points=[irc_b_stp])
    stage_b = first_match(db, stage_b) or stage_b

    stage_ts = StageRow(stationary_points=[optts_calc.stationary_points[0]], is_ts=True)
    stage_ts = first_match(db, stage_ts) or stage_ts

    step = StepRow(
        backward_stage=stage_b, transition_stage=stage_ts, forward_stage=stage_f
    )
    step = first_match(db, step) or step
    step.validations.append(ValidationRow(method="irc", calculation=irc_calc))

    db.add(step)

# %%

# Now we will go through the step and update with optimized end points
freq_model = ModelRow(
    program="orca",
    program_version="6.1.1",
    method="M062X",
    basis="def2-TZVPP",
    calc_type="freq",
)
# Query for existing match
freq_model = first_match(db, freq_model) or freq_model
# TrajectoryRow automatically sorts geometries by index on .geometries call
sorted_geos = irc_calc.output_trajectory.geometries

freq_calc_b = CalculationRow(
    model=freq_model,
    input_geometry=sorted_geos[0],
    input_provenance={"input file": (file_dir / "freq_b.inp").read_text()},
)
freq_calc_b = first_match(db, freq_calc_b) or freq_calc_b

if freq_calc_b.id is None:
    freq_geo_b = GeometryRow.from_xyz_file(
        file_dir / "freq_b.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    freq_geo_b = geometry_match(db, freq_geo_b) or freq_geo_b
    freq_calc_b.output_geometry = freq_geo_b

    db.add(freq_calc_b)

    freq_hess_b = HessianRow(
        geometry=freq_geo_b,
        calculation=freq_calc_b,
        value=helpers.orca_parse_hessian((file_dir / "freq_b.hess").read_text()),
    )
    # We query for the existing stationary point row to update it
    freq_stp_b = StationaryPointRow.partial(
        calculation_id=irc_calc.id, geometry_id=sorted_geos[0].id
    )
    # one_match guarantees one and only one match in the database
    # (adds safety for not picking the wrong row)
    freq_stp_b = one_match(db, freq_stp_b)

    freq_stp_b.geometry = freq_geo_b
    freq_stp_b.hessian = freq_hess_b

    db.add(freq_stp_b)

    ene_calc_b = CalculationRow(
        model=ene_model,
        input_geometry=freq_geo_b,
        input_provenance={"input file": (file_dir / "energy_b.inp").read_text()},
    )
    ene_calc_b = first_match(db, ene_calc_b) or ene_calc_b

    if ene_calc_b.id is None:
        ene_b = EnergyRow(
            geometry=freq_geo_b,
            calculation=ene_calc_b,
            value=helpers.orca_parse_spe((file_dir / "energy_b.log").read_text()),
        )
        db.add(ene_b)

freq_calc_f = CalculationRow(
    model=freq_model,
    input_geometry=sorted_geos[2],
    input_provenance={"input file": (file_dir / "freq_f.inp").read_text()},
)
freq_calc_f = first_match(db, freq_calc_f) or freq_calc_f

if freq_calc_f.id is None:
    freq_geo_f = GeometryRow.from_xyz_file(
        file_dir / "freq_f.xyz", charge=init_geo.charge, spin=init_geo.spin
    )
    freq_geo_f = geometry_match(db, freq_geo_f) or freq_geo_f
    freq_calc_f.output_geometry = freq_geo_f

    db.add(freq_calc_f)

    freq_hess_f = HessianRow(
        geometry=freq_geo_f,
        calculation=freq_calc_f,
        value=helpers.orca_parse_hessian((file_dir / "freq_f.hess").read_text()),
    )
    # We query for the existing stationary point row to update it
    freq_stp_f = StationaryPointRow.partial(
        calculation_id=irc_calc.id, geometry_id=sorted_geos[2].id
    )
    # one_match guarantees one and only one match in the database
    # (adds safety for not picking the wrong row)
    freq_stp_f = one_match(db, freq_stp_f)

    freq_stp_f.geometry = freq_geo_f
    freq_stp_f.hessian = freq_hess_f

    db.add(freq_stp_f)

    ene_calc_f = CalculationRow(
        model=ene_model,
        input_geometry=freq_geo_f,
        input_provenance={"input file": (file_dir / "energy_f.inp").read_text()},
    )
    ene_calc_f = first_match(db, ene_calc_f) or ene_calc_f

    if ene_calc_f.id is None:
        ene_f = EnergyRow(
            geometry=freq_geo_f,
            calculation=ene_calc_f,
            value=helpers.orca_parse_spe((file_dir / "energy_f.log").read_text()),
        )
        db.add(ene_f)
