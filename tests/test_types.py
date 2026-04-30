"""Tests for types module."""

from pathlib import Path

import numpy as np

from autostorage.types import FloatArrayTypeDecorator, PathTypeDecorator


def test__float_array_decorator() -> None:
    """Test the custom FloatArrayTypeDecorator."""
    decorator = FloatArrayTypeDecorator()
    coords = np.array([[0.0, 1.0], [2.0, 3.0]])

    as_list = decorator.process_bind_param(coords, None)
    assert isinstance(as_list, list)
    assert as_list == [[0.0, 1.0], [2.0, 3.0]]

    back_to_arr = decorator.process_result_value(as_list, None)
    assert isinstance(back_to_arr, np.ndarray)
    assert np.allclose(back_to_arr, coords)
    assert back_to_arr.dtype == float


def test__path_decorator() -> None:
    """Test the custom PathTypeDecorator."""
    decorator = PathTypeDecorator()
    work_dir = Path("/home/user/test/calc")

    as_str = decorator.process_bind_param(work_dir, None)
    assert isinstance(as_str, str)
    assert as_str == "/home/user/test/calc"

    back_to_path = decorator.process_result_value(as_str, None)
    assert isinstance(back_to_path, Path)
    assert back_to_path == work_dir
