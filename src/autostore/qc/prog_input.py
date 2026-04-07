"""qc ProgramInput interface."""

import automol
from automol import Geometry
from qcdata import CalcType, DualProgramInput, Model, ProgramArgs, ProgramInput

from ..calcn import Calculation
from ..models import CalculationRow, GeometryRow
from . import structure


def from_auto(
    calc: Calculation | CalculationRow,
    geo: Geometry,
    calctype: CalcType,
) -> DualProgramInput | ProgramInput:
    """
    Generate QCIO ProgramInput from Calculation and Geometry.

    Parameters
    ----------
    calc
        AutoStore Calculation or CalculationRow.
    geo
        AutoMol Geometry.
    calctype
        qcio CalcType.

    Returns
    -------
        QCIO DualProgramInput/ProgramInput
    """
    model = Model(method=calc.method, basis=calc.basis)
    struc = automol.qc.structure.from_geometry(geo)

    data = {
        "keywords": calc.keywords,
        "cmdline_args": calc.cmdline_args,
        "files": calc.files,
        "extras": calc.extras,
    }

    if calc.superprogram:
        return DualProgramInput(
            calctype=calctype,
            structure=struc,
            keywords=calc.superprogram_keywords,
            subprogram=calc.program,
            subprogram_args=ProgramArgs(model=model, **data),  # ty:ignore[invalid-argument-type]
        )

    return ProgramInput(
        calctype=calctype,
        structure=struc,
        model=model,
        **data,  # ty:ignore[invalid-argument-type]
    )


def calc_row(prog_input: ProgramInput, *, prog: str) -> CalculationRow:
    """Extract ProgramInput into a Calculation."""
    data = {
        "cmdline_args": prog_input.cmdline_args,
        "files": prog_input.files,
        "calctype": prog_input.calctype.value,
        "extras": prog_input.extras,
    }

    if isinstance(prog_input, DualProgramInput):
        calc_row = CalculationRow(
            program=prog_input.subprogram,
            method=prog_input.subprogram_args.model.method,
            basis=prog_input.subprogram_args.model.basis,
            keywords=prog_input.subprogram_args.keywords,
            superprogram_keywords=prog_input.keywords,
            superprogram=prog,
            **data,
        )

    else:
        calc_row = CalculationRow(
            program=prog,
            method=prog_input.model.method,
            basis=prog_input.model.basis,
            keywords=prog_input.keywords,
            **data,
        )

    return calc_row


def geom_row(prog_input: ProgramInput) -> GeometryRow:
    """Extract ProgramInput into a Geometry."""
    return structure.geom_row(prog_input.structure)
