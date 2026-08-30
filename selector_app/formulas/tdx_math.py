"""Project-owned NumPy/Pandas implementations of the required TDX functions."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd


def ABS(values: Any) -> np.ndarray:
    return np.asarray(np.abs(values))


def MAX(left: Any, right: Any) -> np.ndarray:
    return np.asarray(np.maximum(left, right))


def MIN(left: Any, right: Any) -> np.ndarray:
    return np.asarray(np.minimum(left, right))


def REF(values: Any, period: int = 1) -> np.ndarray:
    source = np.asarray(values)
    if isinstance(period, bool) or not isinstance(period, (int, np.integer)) or period < 0:
        raise ValueError("REF 周期必须是非负整数")
    return np.asarray(pd.Series(source).shift(int(period)), dtype=float)


def SUM(values: Any, period: int) -> np.ndarray:
    source = np.asarray(values)
    if isinstance(period, bool) or not isinstance(period, (int, np.integer)):
        raise ValueError("SUM 周期必须是整数")
    if period > 0:
        return np.asarray(pd.Series(source).rolling(int(period)).sum(), dtype=float)
    return np.asarray(pd.Series(source).cumsum(), dtype=float)


def HHV(values: Any, period: int) -> np.ndarray:
    return _rolling(values, period, "max")


def LLV(values: Any, period: int) -> np.ndarray:
    return _rolling(values, period, "min")


def MA(values: Any, period: int) -> np.ndarray:
    return _rolling(values, period, "mean")


def _rolling(values: Any, period: int, operation: str) -> np.ndarray:
    source = np.asarray(values)
    if isinstance(period, bool) or not isinstance(period, (int, np.integer)) or period <= 0:
        raise ValueError("滚动周期必须是大于 0 的整数")
    rolling = pd.Series(source).rolling(int(period))
    if operation == "max":
        return np.asarray(rolling.max(), dtype=float)
    if operation == "min":
        return np.asarray(rolling.min(), dtype=float)
    return np.asarray(rolling.mean(), dtype=float)


def EMA(values: Any, period: int) -> np.ndarray:
    if isinstance(period, bool) or not isinstance(period, (int, np.integer)) or period <= 0:
        raise ValueError("EMA 周期必须是大于 0 的整数")
    return np.asarray(
        pd.Series(np.asarray(values)).ewm(span=int(period), adjust=False).mean(), dtype=float
    )


def SMA(values: Any, period: float, weight: float = 1) -> np.ndarray:
    if isinstance(period, bool) or not isinstance(period, (int, float, np.integer, np.floating)):
        raise ValueError("SMA 周期必须是数字")
    if not np.isfinite(period) or period <= 0:
        raise ValueError("SMA 周期必须是大于 0 的有限数字")
    if not np.isfinite(weight) or weight <= 0:
        raise ValueError("SMA 权重必须是大于 0 的有限数字")
    result = (
        pd.Series(np.asarray(values, dtype=float))
        .ewm(alpha=float(weight) / float(period), adjust=False)
        .mean()
        .to_numpy(dtype=float)
    )
    return cast(np.ndarray, result)


def COUNT(values: Any, period: int) -> np.ndarray:
    return SUM(np.asarray(values, dtype=bool), period)


def BARSLAST(values: Any) -> np.ndarray:
    source = np.asarray(values, dtype=bool)
    result = np.empty(len(source), dtype=int)
    elapsed = 0
    for index, matched in enumerate(source):
        if matched:
            elapsed = 0
        else:
            elapsed += 1
        result[index] = elapsed
    return result


def CROSS(left: Any, right: Any) -> np.ndarray:
    crossed = np.asarray(left) > np.asarray(right)
    if crossed.size == 0:
        return np.array([], dtype=bool)
    return np.concatenate((np.array([False]), np.logical_not(crossed[:-1]) & crossed[1:]))


class _TdxMath:
    ABS = staticmethod(ABS)
    MAX = staticmethod(MAX)
    MIN = staticmethod(MIN)
    REF = staticmethod(REF)
    SUM = staticmethod(SUM)
    HHV = staticmethod(HHV)
    LLV = staticmethod(LLV)
    MA = staticmethod(MA)
    EMA = staticmethod(EMA)
    SMA = staticmethod(SMA)
    COUNT = staticmethod(COUNT)
    BARSLAST = staticmethod(BARSLAST)
    CROSS = staticmethod(CROSS)


MYTT = _TdxMath()
