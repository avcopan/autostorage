"""FastAPI app serving an AutoStorage database as JSON, plus the built front end."""

import uuid
from pathlib import Path

import autogeom
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, select

from ..database import Database
from ..models import GeometryRow

STATIC_DIR = Path(__file__).parent / "static"  # filled by `pixi run gui-build`


class GeometrySummary(SQLModel):
    """One row of the geometry list, as the front end receives it."""

    id: uuid.UUID | None  # the type of `GeometryRow.id`; never None once saved
    formula: str
    natoms: int


def create_app(path: str | Path) -> FastAPI:
    """Return an app serving the database at `path`."""
    db = Database(path)
    app = FastAPI(title="AutoStorage")

    @app.get("/api/geometries")
    def list_geometries() -> list[GeometrySummary]:
        with db.session() as session:
            return [
                GeometrySummary(
                    id=geo.id, formula=autogeom.formula(geo), natoms=len(geo.symbols)
                )
                for geo in session.exec(select(GeometryRow))
            ]

    # Serve the built front end at `/` (after the API routes, so they take precedence)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")

    return app
