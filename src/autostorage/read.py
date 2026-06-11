"""utility read functions."""

from pathlib import Path

from automatics import geom

from .models import GeometryRow


def xyz_file(
    path: str | Path, *, charge: int | None = None, spin: int | None = None
) -> GeometryRow:
    """Read an xyz formatted file into the database."""
    path = path if isinstance(path, Path) else Path(path)
    geo = geom.from_xyz_block(path.read_text(), spin=spin, charge=charge)
    return GeometryRow.model_validate(geo)
