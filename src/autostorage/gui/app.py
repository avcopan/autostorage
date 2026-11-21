"""FastAPI back end for the GUI, which also serves the built front end."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"  # filled by `pixi run gui-build`


def create_app() -> FastAPI:
    """Return the GUI app."""
    app = FastAPI(title="AutoStorage")

    @app.get("/api/hello")
    def hello() -> dict[str, str]:
        return {"message": "Hello from FastAPI!"}

    # Serve the built front end at `/` (after the API routes, so they take precedence)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")

    return app
