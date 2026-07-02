"""Parse and store an example ORCA transition point workflow."""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyparsing as pp
from automol import Identity
from pyparsing import pyparsing_common as ppc
from sqlalchemy.exc import NoResultFound
from sqlmodel import SQLModel, select

from autostorage import (
    CalcType,
    CalculationRow,
    Database,
    EnergyRow,
    GeometryRow,
    ModelRow,
    StageRow,
    StationaryPointRow,
    StepRow,
    ValidationRow,
)
from autostorage.types import Role


# ===============================================
# Helper functions
# ===============================================
def resolve_hashed_row[RowT: SQLModel](db: Database, row: RowT) -> RowT:
    """Return existing row matching hash or provided row if not found."""
    stmt = select(type(row)).where(type(row).hash == row.hash)  # ty:ignore[unresolved-attribute]
    try:
        return db.exec_one(stmt)
    except NoResultFound:
        return row


def query_stationary(
    db: Database, calc: CalculationRow, input_geo: GeometryRow
) -> StationaryPointRow | None:
    """Query for existing stationary point rows."""
    db.flush()
    stmt = (
        select(StationaryPointRow)
        .join(CalculationRow)
        .join(GeometryRow)
        .where(
            CalculationRow.model_id == calc.model_id,
            CalculationRow.input_provenance == calc.input_provenance,
            GeometryRow.hash == input_geo.hash,
        )
    )
    return db.exec_first(stmt)


def query_energy(
    db: Database, calc: CalculationRow, input_geo: GeometryRow
) -> EnergyRow | None:
    """Query for existing stationary point rows."""
    db.flush()
    stmt = (
        select(EnergyRow)
        .join(CalculationRow)
        .join(GeometryRow)
        .where(
            CalculationRow.model_id == calc.model_id,
            CalculationRow.input_provenance == calc.input_provenance,
            GeometryRow.hash == input_geo.hash,
        )
    )
    return db.exec_first(stmt)


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
data_path = Path.cwd() / "data/orca_transition"

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
# TS Optimization
# ===============================================
optts_prov = {
    "keywords": ["DEFGRID3", "TightSCF", "SlowConv", "TightOpt", "Freq"],
    "geom": {"Recalc_Hess": 5, "MaxIter": 500},
}

guess_xyz = (
    GeometryRow.from_xyz_file(data_path / "guess.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)

optts_xyz = (
    GeometryRow.from_xyz_file(data_path / "freq.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
optts_ident = Identity.from_geometry(optts_xyz, algorithm="rdkit inchi")
optts_stp = StationaryPointRow.query(
    db, ident=optts_ident, model=m062x, prov=optts_prov
)
if not optts_stp:
    optts_calc = CalculationRow(
        model=m062x, calc_type=CalcType.OPT_TS, input_provenance=optts_prov
    ).save(db)
    optts_calc.geometry_link(guess_xyz, Role.INPUT).save(db)
    optts_calc.geometry_link(optts_xyz, Role.OUTPUT).save(db)

    optts_stp = optts_xyz.stationary_point(optts_calc, order=1).save(db)
    optts_xyz.gradient(optts_calc, parse_gradient(data_path / "freq.engrad")).save(db)
    optts_xyz.hessian(optts_calc, parse_hessian(data_path / "freq.hess")).save(db)

    optts_calc.output_provenance = parse_provenance(data_path / "freq.property.txt")

db.commit()

# ===============================================
# TS Energy
# ===============================================
ene_prov = {"auxiliary_sets": ["cc-pVDZ-F12-CABS", "cc-pVTZ/c"]}

ene_res = EnergyRow.query(db, geo=optts_xyz, model=ccsdt, prov=ene_prov)
if not ene_res:
    ene_calc = CalculationRow(
        model=ccsdt, calc_type=CalcType.ENERGY, input_provenance=ene_prov
    ).save(db)
    ene_calc.geometry_link(optts_xyz, Role.INPUT).save(db)

    optts_xyz.energy(ene_calc, value=parse_spe(data_path / "energy.log")).save(db)

    ene_calc.output_provenance = parse_provenance(data_path / "energy.property.txt")

# ===============================================
# IRC Calculation
# ===============================================
irc_f_xyz = (
    GeometryRow.from_xyz_file(data_path / "irc_IRC_F.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
irc_f_ident = Identity.from_geometry(irc_f_xyz, algorithm="rdkit inchi")
irc_f_stp = StationaryPointRow.query(db, ident=irc_f_ident, model=m062x)

irc_b_xyz = (
    GeometryRow.from_xyz_file(data_path / "irc_IRC_B.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
irc_b_ident = Identity.from_geometry(irc_b_xyz, algorithm="rdkit inchi")
irc_b_stp = StationaryPointRow.query(db, ident=irc_b_ident, model=m062x)

if not irc_f_stp or not irc_b_stp:
    irc_calc = CalculationRow(model=m062x, calc_type=CalcType.IRC).save(db)
    irc_calc.geometry_link(optts_xyz, Role.INPUT).save(db)
    irc_calc.geometry_link(irc_f_xyz, Role.OUTPUT).save(db)
    irc_calc.geometry_link(irc_b_xyz, Role.OUTPUT).save(db)

    irc_t_stage = StageRow(stationaries=[optts_stp], is_ts=True).save(db)

    irc_f_stp = irc_f_stp or irc_f_xyz.stationary_point(irc_calc, is_pseudo=True).save(
        db
    )
    irc_f_stage = StageRow(stationaries=[irc_f_stp]).save(db)

    irc_b_stp = irc_b_stp or irc_b_xyz.stationary_point(irc_calc, is_pseudo=True).save(
        db
    )
    irc_b_stage = StageRow(stationaries=[irc_b_stp]).save(db)

    irc_step = StepRow(
        stage1=irc_b_stage, stage2=irc_f_stage, stage_ts=irc_t_stage
    ).save(db)

    ValidationRow(method="irc", calculation=irc_calc, step=irc_step).save(db)

db.commit()

# ===============================================
# Forward optimization / frequency / energy
# ===============================================
opt_prov = {
    "keywords": ["DEFGRID3", "TightSCF", "SlowConv", "TightOpt", "Freq"],
    "geom": {"Recalc_Hess": 5, "MaxIter": 500},
}

opt_f_xyz = (
    GeometryRow.from_xyz_file(data_path / "freq_f.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
opt_f_ident = Identity.from_geometry(opt_f_xyz, algorithm="rdkit inchi")
opt_f_stp = StationaryPointRow.query(db, ident=opt_f_ident, model=m062x, prov=opt_prov)
if not opt_f_stp:
    opt_f_calc = CalculationRow(
        model=m062x, calc_type=CalcType.OPT, input_provenance=opt_prov
    ).save(db)
    opt_f_calc.geometry_link(irc_f_xyz, Role.INPUT).save(db)
    opt_f_calc.geometry_link(opt_f_xyz, Role.OUTPUT).save(db)

    opt_f_xyz.gradient(opt_f_calc, parse_gradient(data_path / "freq_f.engrad")).save(db)
    opt_f_xyz.hessian(opt_f_calc, parse_hessian(data_path / "freq_f.hess")).save(db)

    opt_f_stp = opt_f_xyz.stationary_point(opt_f_calc).save(db)

db.commit()

ene_prov = {"auxiliary_sets": ["cc-pVDZ-F12-CABS", "cc-pVTZ/c"]}

ene_res = EnergyRow.query(db, geo=opt_f_xyz, model=ccsdt, prov=ene_prov)
if not ene_res:
    ene_f_calc = CalculationRow(
        model=ccsdt, calc_type=CalcType.ENERGY, input_provenance=ene_prov
    ).save(db)
    ene_f_calc.geometry_link(opt_f_xyz, Role.INPUT).save(db)
    opt_f_xyz.energy(ene_f_calc, value=parse_spe(data_path / "energy_f.log")).save(db)

    ene_calc.output_provenance = parse_provenance(data_path / "energy_f.property.txt")

db.commit()

# ===============================================
# Backward optimization / frequency / energy
# ===============================================
opt_prov = {
    "keywords": ["DEFGRID3", "TightSCF", "SlowConv", "TightOpt", "Freq"],
    "geom": {"Recalc_Hess": 5, "MaxIter": 500},
}

opt_b_xyz = (
    GeometryRow.from_xyz_file(data_path / "freq_b.xyz", charge=0, spin=1)
    .canonical_form()
    .resolve(db)
    .save(db)
)
opt_b_ident = Identity.from_geometry(opt_b_xyz, algorithm="rdkit inchi")
opt_b_stp = StationaryPointRow.query(db, ident=opt_b_ident, model=m062x, prov=opt_prov)
if not opt_b_stp:
    opt_b_calc = CalculationRow(
        model=m062x, calc_type=CalcType.OPT, input_provenance=opt_prov
    ).save(db)
    opt_b_calc.geometry_link(irc_b_xyz, Role.INPUT).save(db)
    opt_b_calc.geometry_link(opt_b_xyz, Role.OUTPUT).save(db)

    opt_b_xyz.gradient(opt_b_calc, parse_gradient(data_path / "freq_b.engrad")).save(db)
    opt_b_xyz.hessian(opt_b_calc, parse_hessian(data_path / "freq_b.hess")).save(db)

    opt_b_stp = opt_b_xyz.stationary_point(opt_b_calc).save(db)

db.commit()

ene_prov = {"auxiliary_sets": ["cc-pVDZ-F12-CABS", "cc-pVTZ/c"]}

ene_res = EnergyRow.query(db, geo=opt_b_xyz, model=ccsdt, prov=ene_prov)
if not ene_res:
    ene_b_calc = CalculationRow(
        model=ccsdt, calc_type=CalcType.ENERGY, input_provenance=ene_prov
    ).save(db)
    ene_b_calc.geometry_link(opt_b_xyz, Role.INPUT).save(db)
    opt_b_xyz.energy(ene_b_calc, value=parse_spe(data_path / "energy_b.log")).save(db)

    ene_calc.output_provenance = parse_provenance(data_path / "energy_b.property.txt")

db.commit()

# ===============================================
# Build a new step
# ===============================================
optts_stage = StageRow.query(db, [optts_stp], is_ts=True) or StageRow(
    stationaries=[optts_stp], is_ts=True
).save(db)
opt_f_stage = StageRow.query(db, [opt_f_stp]) or StageRow(
    stationaries=[opt_f_stp]
).save(db)
opt_b_stage = StageRow.query(db, [opt_b_stp]) or StageRow(
    stationaries=[opt_b_stp]
).save(db)

step2 = StepRow.query(db, opt_b_stage, opt_f_stage, optts_stage) or StepRow(
    stage1=opt_b_stage, stage2=opt_f_stage, stage_ts=optts_stage
).save(db)


db.commit()
