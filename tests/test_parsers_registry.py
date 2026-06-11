"""Tests for parsers registry."""

from enum import Enum

import pytest
from qcdata import CalcType

from autostorage.models.calculation import CalculationRow
from autostorage.parsers.registry import ParserSpec, register
from autostorage.parsers.registry import registry as real_registry


class MockFileType(Enum):
    """Mock file types."""

    STDOUT = "stdout"
    INP = ".inp"


class RegistryVerifier:
    """A simple verifier to hold our captured records."""

    def __init__(self) -> None:
        self.records: list[ParserSpec] = []


@pytest.fixture
def mock_registry(monkeypatch) -> RegistryVerifier:  # noqa: ANN001, D103
    verifier = RegistryVerifier()

    monkeypatch.setattr(real_registry, "register", verifier.records.append)

    return verifier


def test__register_decorator_success(mock_registry: RegistryVerifier) -> None:
    """Test successful decorator registration."""

    @register(
        filetype=MockFileType.STDOUT,
        target_tables=[CalculationRow],
        calctypes=[CalcType.energy, CalcType.optimization],
    )
    def dummy_parser(contents: str) -> str:  # noqa: ARG001
        return "success"

    assert dummy_parser("data") == "success"

    assert len(mock_registry.records) == 1

    assert mock_registry.records[0].parser == dummy_parser
    assert mock_registry.records[0].calctypes == [
        CalcType.energy,
        CalcType.optimization,
    ]
