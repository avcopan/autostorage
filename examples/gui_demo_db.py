"""Write a small demo database for GUI development: `pixi run gui-demo-db`."""

import sys
from pathlib import Path

import autogeom

from autostorage import Database, GeometryRow

SMILES = ["O", "CO", "C=C", "c1ccccc1", "CC(=O)O", "[OH]"]

path = Path(sys.argv[1] if len(sys.argv) > 1 else "demo.db")
path.unlink(missing_ok=True)  # start fresh on every run
with Database(path) as db, db.session() as session:
    for smi in SMILES:
        geo = autogeom.from_smiles(smi)
        session.add(GeometryRow(**geo.model_dump()))
    session.commit()
print(f"Wrote {len(SMILES)} geometries to {path}")
