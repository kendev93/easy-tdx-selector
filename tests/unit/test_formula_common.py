from __future__ import annotations

import numpy as np

from selector_app.formulas.common import safe_divide


def test_safe_divide_returns_nan_for_zero_denominator() -> None:
    result = safe_divide(np.array([2.0, 0.0, 4.0]), np.array([1.0, 0.0, 2.0]))

    assert result[0] == 2.0
    assert np.isnan(result[1])
    assert result[2] == 2.0


def test_safe_divide_preserves_negative_denominator() -> None:
    result = safe_divide(np.array([4.0]), np.array([-2.0]))

    assert result.tolist() == [-2.0]


def test_safe_divide_handles_empty_arrays() -> None:
    result = safe_divide(np.array([], dtype=float), np.array([], dtype=float))

    assert result.size == 0
