"""calculate hessian properties."""

import numpy.typing as npt
from automol import geom

from ..models import HessianRow


def vibrational_analysis(
    hess: HessianRow, *, trans: bool = False, rot: bool = False
) -> tuple[tuple[float, ...], npt.NDArray]:
    """Calculate frequencies and vibrational modes from a Hessian matrix.

    Parameters
    ----------
    hess
        Instance of a HessianRow.
    trans
        If True, keep translational modes.
    rot
        If True, keep rotational modes.

    Returns
    -------
    frequencies
        Vibrational frequencies.
    modes
        Vibrational modes.

    Raises
    ------
    ValueError
        `Hessian shape is not (3N, 3N)`.
    """
    return geom.vibrational_analysis(
        geo=hess.geometry, hess=hess.value, trans=trans, rot=rot
    )
