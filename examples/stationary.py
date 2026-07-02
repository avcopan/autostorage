"""Parse and store an example ORCA stationary point workflow."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyparsing as pp
from automol import Identity
from pyparsing import pyparsing_common as ppc

from autostorage import (
    CalcType,
    CalculationRow,
    Database,
    EnergyRow,
    GeometryRow,
    ModelRow,
    Role,
    StationaryPointRow,
    TrajectoryRow,
)


# ===============================================
# Helper functions
# ===============================================
def parse_xyz_traj(
    xyz_file: str | Path, charge: int, spin: int
) -> Iterator[GeometryRow]:
    """Yield GeometryRow instances from an xyz file."""
    xyz_block = Path(xyz_file).read_text().strip()
    if not xyz_block:
        msg = "Provided xyz block is empty."
        raise ValueError(msg)

    frames = re.split(r"(?=\n\s*\d+\s*\n)", f"\n{xyz_block}")
    for frame in frames:
        frame_block = frame.strip()
        if not frame_block:
            continue

        yield GeometryRow.from_xyz_block(frame_block, charge=charge, spin=spin)


def parse_spe(log_file: str | Path) -> float:
    """Parse final single point energy from orca stdout."""
    text_block = Path(log_file).read_text()
    match = re.search(r"FINAL SINGLE POINT ENERGY\s+([-+]?\d+\.\d+)", text_block)

    if match:
        return float(match.group(1))

    msg = "Final single point energy line could not be parsed."
    raise ValueError(msg)


INTEGER = ppc.integer.set_parse_action(lambda t: int(t[0]))
FLOAT_NUMBER = ppc.sci_real.set_parse_action(lambda t: float(t[0]))


def parse_gradient(grad_file: str | Path) -> list[float]:
    """Parse energy gradient from orca .engrad."""
    text_block = Path(grad_file).read_text()
    header = (
        pp.Literal("# The current gradient in Eh/bohr")
        + pp.LineEnd()
        + pp.Literal("#")
        + pp.LineEnd()
    )
    footer = pp.Literal("#")

    gradient_parser = (
        pp.SkipTo(header) + header + pp.OneOrMore(FLOAT_NUMBER)("values") + footer
    )

    results = gradient_parser.parse_string(text_block)

    return list(results["values"])


def parse_hessian(hess_file: str | Path) -> list[list[float]]:
    """Parse Hessian from orca .hess."""
    text_block = Path(hess_file).read_text()
    # Find the $hessian section
    match = re.search(r"\$hessian\s+(\d+)\s+(.*?)\$", text_block, re.DOTALL)
    if not match:
        msg = "No $hessian section found"
        raise ValueError(msg)

    dimension = int(match.group(1))
    body = match.group(2)

    hess: list[list[float]] = [[] for _ in range(dimension)]

    # Data line: integer index followed by floats
    data_line_re = re.compile(
        r"^\s+(\d+)((?:\s+[+-]?\d+\.\d+E[+-]\d+)+)\s*$", re.MULTILINE
    )

    for line in body.splitlines():
        m = data_line_re.match(line)
        if m:
            row_idx = int(m.group(1))
            vals = [float(v) for v in m.group(2).split()]
            hess[row_idx].extend(vals)

    return hess


def parse_provenance(property_file: str | Path) -> dict[str, dict[str, Any]]:
    """Parse provenance blocks starting with $Calculation into dictionaries."""
    text = Path(property_file).read_text()
    result = {}

    block_pattern = re.compile(r"\$(\w+)\s*(.*?)\s*\$End", re.DOTALL)
    attr_pattern = re.compile(r"&(\w+)(?:\s*\[&Type\s*\"(\w+)\"\])?\s+([^\n]+)")

    for block_match in block_pattern.finditer(text):
        block_name = block_match.group(1)

        if not block_name.startswith("Calculation"):
            continue

        block_content = block_match.group(2)
        block_dict = {}

        for attr_match in attr_pattern.finditer(block_content):
            key = attr_match.group(1)
            type_hint = attr_match.group(2)
            raw_value = attr_match.group(3).strip()

            if type_hint == "Integer":
                value = int(raw_value)
            elif type_hint == "Double":
                value = float(raw_value)
            else:
                try:
                    value = int(raw_value)
                except ValueError:
                    try:
                        value = float(raw_value)
                    except ValueError:
                        value = raw_value

            block_dict[key] = value

        result[block_name] = block_dict

    return result


# ===============================================
# File setup
# ===============================================
data_path = Path.cwd() / "data/orca_stationary"

test_path = Path("test.db")

db = Database(test_path)

# ===============================================
# Declare models
# ===============================================
xtb = (
    ModelRow(program="orca", program_version="6.1.1", method="xtb").resolve(db).save(db)
)
wb97x_3c = (
    ModelRow(program="orca", program_version="6.1.1", method="wb97x-3c")
    .resolve(db)
    .save(db)
)
m062x = (
    ModelRow(
        program="orca", program_version="6.1.1", method="m062x", basis="def2-TZVPP"
    )
    .resolve(db)
    .save(db)
)
ccsdt = (
    ModelRow(
        program="orca",
        program_version="6.1.1",
        method="CCSD(T)-F12/RI",
        basis="cc-pVDZ-F12",
    )
    .resolve(db)
    .save(db)
)

# ===============================================
# xtb/GOAT calculation
# ===============================================
# Read initial xyz file, convert to canonical form, and check database for match
init_xyz = (
    GeometryRow.from_xyz_file(data_path / "init.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)

# Read optimized goat global minimum
goat_xyz = (
    GeometryRow.from_xyz_file(data_path / "goat.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
goat_ident = Identity.from_geometry(goat_xyz, algorithm="rdkit inchi")
goat_stp = StationaryPointRow.query(db, ident=goat_ident, model=xtb)
if not goat_stp:
    goat_calc = CalculationRow(model=xtb, calc_type=CalcType.CONFORMER).save(db)

    init_xyz.calculation_link(goat_calc, Role.INPUT).save(db)

    goat_xyz.calculation_link(goat_calc, Role.OUTPUT).save(db)
    goat_xyz.stationary_point(goat_calc).save(db)

    # Parse the trajectory
    goat_traj = TrajectoryRow().save(db)
    goat_traj.calculation_link(goat_calc, Role.OUTPUT).save(db)

    for geo in parse_xyz_traj(data_path / "goat.finalensemble.xyz", charge=0, spin=1):
        traj_geo = geo.canonical_form().resolve(db).save(db)
        traj_geo.calculation_link(goat_calc, Role.OUTPUT).save(db)
        traj_geo.trajectory_link(goat_traj).save(db)
        traj_geo.stationary_point(goat_calc, is_pseudo=True).save(db)

    # Update goat_calc with output provenance
    goat_calc.output_provenance = parse_provenance(data_path / "goat.property.txt")

# Commit everything up to this point
db.commit()

# ===============================================
# Initial optimization
# ===============================================
opt_xyz = (
    GeometryRow.from_xyz_file(data_path / "opt.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
opt_ident = Identity.from_geometry(opt_xyz, algorithm="rdkit inchi")
opt_stp = StationaryPointRow.query(
    db, ident=opt_ident, model=wb97x_3c, calc_type=CalcType.OPT
)
if not opt_stp:
    opt_calc = CalculationRow(model=wb97x_3c, calc_type=CalcType.OPT).save(db)
    opt_calc.geometry_link(goat_xyz, Role.INPUT).save(db)
    opt_calc.geometry_link(opt_xyz, Role.OUTPUT).save(db)

    opt_xyz.gradient(opt_calc, parse_gradient(data_path / "opt.engrad")).save(db)
    opt_xyz.stationary_point(opt_calc).save(db)

    opt_calc.output_provenance = parse_provenance(data_path / "opt.property.txt")

db.commit()

# ===============================================
# Frequency + optimization
# ===============================================
freq_prov = {
    "cmdline_args": ["DEFGRID3", "TightSCF", "SlowConv", "Opt", "NumFreq"],
    "geom": {"MaxIter": 500},
}

freq_xyz = (
    GeometryRow.from_xyz_file(data_path / "freq.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
freq_ident = Identity.from_geometry(freq_xyz, algorithm="rdkit inchi")
freq_stp = StationaryPointRow.query(db, ident=freq_ident, model=m062x, prov=freq_prov)
if not freq_stp:
    freq_calc = CalculationRow(
        model=m062x, calc_type=CalcType.OPT, input_provenance=freq_prov
    ).save(db)
    freq_calc.geometry_link(opt_xyz, Role.INPUT).save(db)
    freq_calc.geometry_link(freq_xyz, Role.OUTPUT).save(db)

    freq_xyz.gradient(freq_calc, parse_gradient(data_path / "freq.engrad")).save(db)
    freq_xyz.hessian(freq_calc, parse_hessian(data_path / "freq.hess")).save(db)
    freq_xyz.stationary_point(freq_calc).save(db)

    freq_calc.output_provenance = parse_provenance(data_path / "freq.property.txt")

db.commit()

# ===============================================
# Stationary Point Energy
# ===============================================
ene_prov = {"auxiliary_sets": ["cc-pVDZ-F12-CABS", "cc-pVTZ/c"]}

ene_res = EnergyRow.query(db, geo=freq_xyz, model=ccsdt, prov=ene_prov)
if not ene_res:
    ene_calc = CalculationRow(
        model=ccsdt, calc_type=CalcType.ENERGY, input_provenance=ene_prov
    ).save(db)

    freq_xyz.calculation_link(ene_calc, Role.INPUT).save(db)
    freq_xyz.energy(ene_calc, value=parse_spe(data_path / "energy.log")).save(db)

db.commit()
