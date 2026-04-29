"""autostore tests."""

import autostore


def test_stub() -> None:
    """Stub test to ensure the test suite runs."""
    print(autostore.__version__)  # noqa: T201


def test__greet() -> None:
    """Test the greet function."""
    assert autostore.greet("World") == "Hello, World!"


def test__greet_jim() -> None:
    """Test the greet_jim function."""
    assert autostore.greet_jim() == "Hello, Jim!"
