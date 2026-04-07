"""QCIO Structure interface."""

import pint
from qcdata import Structure

from ..models import GeometryRow


def geom_row(struc: Structure) -> GeometryRow:
    """
    Generate Geometry from QCIO Structure.

    Parameters
    ----------
    struc
        QCIO Structure.

    Returns
    -------
        GeometryRow
    """
    return GeometryRow(
        symbols=struc.symbols,
        coordinates=struc.geometry * pint.Quantity("bohr").m_as("angstrom"),
        charge=struc.charge,
        spin=struc.multiplicity - 1,
    )
