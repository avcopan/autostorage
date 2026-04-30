"""Calculation metadata."""

from typing import Any

from pydantic import BaseModel, Field

from .util import CalculationDict, hash_from_dict, project_keywords


class Calculation(BaseModel):
    """Calculation input parameters and metadata.

    Attributes
    ----------
    # - Program Input -------
    program
        Quantum chemistry program used (psi4, ORCA, ...)
    program_keywords
        (Optional) Quantum chemistry program keywords.
    super_program
        (Optional) Geometry optimizer program (geomeTRIC, ...).
    super_keywords
        (Optional) Geometry optimizer keywords.
    cmdline_args
        (Optional) Command line arguments.
    input
        (Optional) Input file. [ PLACEHOLDER ]
    files
        (Optional) Additional input files. [ PLACEHOLDER ]
    # - Methods -------------
    calc_type
        Calculation type (energy, optimization, ...)
    method
        Computational method (B3LYP, MP2, ...)
    basis
        (Optional) Basis set.
    """

    # - Program Input -------
    program: str
    program_keywords: dict[str, Any] = Field(default_factory=dict)
    super_program: str | None = Field(default=None)
    super_keywords: dict[str, Any] = Field(default_factory=dict)
    cmdline_args: list[str] = Field(default_factory=list)

    # - Methods -------------
    calc_type: str | None = Field(default=None)
    method: str
    basis: str | None = Field(default=None)


def projected_hash(calc: Calculation, template: Calculation | CalculationDict) -> str:
    """
    Project calculation onto template and generate hash.

    Parameters
    ----------
    calc
        Calculation metadata.
    template
        Calculation metadata template.

    Returns
    -------
        Hash string.
    """
    calc_dct = project(calc, template)
    return hash_from_dict(calc_dct)


def project(
    calc: Calculation, template: Calculation | CalculationDict
) -> CalculationDict:
    """
    Project calculation onto template.

    Parameters
    ----------
    calc
        Calculation metadata.
    template
        Calculation metadata template.

    Returns
    -------
        Projected calculation dictionary.
    """
    # Dump template to dictionary
    template_dct = (
        template.model_dump(exclude_unset=True)
        if isinstance(template, Calculation)
        else template
    )
    # Work on a deep copy to avoid accidental modifications
    calc_copy = calc.model_copy(deep=True)
    # Project program_keywords if 'keywords' is in the template
    if "program_keywords" in template_dct:
        calc_copy.program_keywords = project_keywords(
            calc_copy.program_keywords,
            template=template_dct.get("program_keywords", {}),
        )
    if "super_keywords" in template_dct:
        calc_copy.super_keywords = project_keywords(
            calc_copy.super_keywords, template=template_dct.get("super_keywords", {})
        )
    # Include fields from template
    return calc_copy.model_dump(exclude_none=True, include=set(template_dct.keys()))
