"""Tests for the GUI's FastAPI back end."""

from fastapi.testclient import TestClient

from autostorage.gui.app import create_app


def test_hello() -> None:
    """The hello endpoint answers."""
    response = TestClient(create_app()).get("/api/hello")
    assert response.json() == {"message": "Hello from FastAPI!"}
