"""Tests for the GUI's FastAPI back end."""

from pathlib import Path

import autogeom
from fastapi.testclient import TestClient

from autostorage import Database, GeometryRow
from autostorage.gui.app import create_app


class TestListGeometries:
    """Tests for the `/api/geometries` endpoint."""

    def test_list(self, tmp_path: Path) -> None:
        """Each geometry is listed with its formula and atom count."""
        path = tmp_path / "test.db"
        with Database(path) as db, db.session() as session:
            session.add(GeometryRow(**autogeom.from_smiles("CO").model_dump()))
            session.commit()
        client = TestClient(create_app(path))
        (geo,) = client.get("/api/geometries").json()
        assert geo["formula"] == "CH4O"
        assert geo["natoms"] == 6
