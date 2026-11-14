"""Types module tests."""

import zlib

import numpy as np
import pytest

from autostorage.types import (
    CompressedArrayTypeDecorator,
    CompressedJSONTypeDecorator,
    _decompress,
)


def test_decompress_limit() -> None:
    """Decompression beyond the size limit is refused."""
    data = zlib.compress(b"0" * 1000)

    assert _decompress(data, max_size=1000) == b"0" * 1000
    with pytest.raises(ValueError, match="limit"):
        _decompress(data, max_size=999)


def test_decompress_truncated() -> None:
    """A truncated compressed stream is refused."""
    data = zlib.compress(b"0" * 1000)

    with pytest.raises(ValueError, match="truncated"):
        _decompress(data[:-4])


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_array_decorator_preserves_dtype(dtype: type[np.floating]) -> None:
    """With `dtype=None`, the input array's dtype is preserved."""
    decorator = CompressedArrayTypeDecorator(dtype=None)
    value = np.arange(6, dtype=dtype).reshape(2, 3)

    stored = decorator.process_bind_param(value, None)
    loaded = decorator.process_result_value(stored, None)

    assert loaded is not None
    assert loaded.dtype == dtype
    np.testing.assert_array_equal(loaded, value)


@pytest.mark.parametrize("value", [None, {}, {"a": [1, 2.5, None], "b": {"c": "d"}}])
def test_json_decorator_round_trip(value: object) -> None:
    """JSON values survive a compress/decompress round trip."""
    decorator = CompressedJSONTypeDecorator()

    stored = decorator.process_bind_param(value, None)

    assert decorator.process_result_value(stored, None) == value
