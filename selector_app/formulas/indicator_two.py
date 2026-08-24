"""通达信指标二：成本、饱和度与中短期线。"""

from __future__ import annotations

import numpy as np
import pandas as pd
from easy_tdx import MyTT

from .common import (
    build_formula_result,
    dynamic_ref,
    empty_formula_result,
    numeric_column,
    safe_divide,
)
from .types import FormulaResult

FORMULA_ID = "indicator_two"
DISPLAY_NAME = "指标二 · 成本与饱和度"
MINIMUM_BARS = 34
RECOMMENDED_BARS = 120
SIGNAL_NAMES = (
    "start",
    "end",
    "saturation_hot",
    "new_high_breakout",
    "short_above_mid_long",
    "short_below_mid_long",
)


def _weighted_x(a: np.ndarray) -> np.ndarray:
    """Keep the source's skipped REF(A,19) and explicit REF(A,20)."""

    result = np.zeros(len(a), dtype=float)
    for offset in range(19):  # A through REF(A,18): weights 20 through 2
        result += (20 - offset) * MyTT.REF(a, offset)
    result += MyTT.REF(a, 20)  # deliberately no REF(A,19)
    return result / 210


def calculate_indicator_two(frame: pd.DataFrame) -> FormulaResult:
    if len(frame) < MINIMUM_BARS:
        return empty_formula_result(
            formula_id=FORMULA_ID,
            display_name=DISPLAY_NAME,
            minimum_bars=MINIMUM_BARS,
            recommended_bars=RECOMMENDED_BARS,
            signal_names=SIGNAL_NAMES,
            data_length=len(frame),
        )

    open_ = numeric_column(frame, "open")
    high = numeric_column(frame, "high")
    low = numeric_column(frame, "low")
    close = numeric_column(frame, "close")
    amount = numeric_column(frame, "amount")

    short_cost = MyTT.EMA(close, 17)
    a = (3 * close + low + open_ + high) / 6
    x = _weighted_x(a)
    # Regression-only counterfactual used by tests/documentation to protect the gap.
    x_with_ref_19 = x + 19 * MyTT.REF(a, 19)
    mid_cost = MyTT.EMA(x, 13)

    var1 = np.ones(len(close))
    var2 = MyTT.LLV(low, 10)
    var3 = MyTT.HHV(high, 25)
    n1 = np.full(len(close), 5.0)
    n4 = np.full(len(close), 34.0)

    cq_denominator = MyTT.HHV(close, 34) - MyTT.LLV(low, 34)
    cq = 100 * safe_divide(close - MyTT.LLV(low, 34), cq_denominator)
    amount_over_close = safe_divide(amount, close)
    amount_high_over_close_high = safe_divide(MyTT.HHV(amount, 34), MyTT.HHV(close, 34))
    sat = safe_divide(amount_over_close, amount_high_over_close_high)
    saturation = np.minimum(np.where(sat > 1, 1, sat), 1) * 100

    w1 = close == MyTT.HHV(close, 20)
    w2 = MyTT.BARSLAST(w1)
    # Both source IF branches are REF(C,W2), so dynamic_ref is equivalent and clearer.
    w3 = dynamic_ref(close, w2)
    w4 = MyTT.CROSS(close, MyTT.REF(w3, 1))

    mid_term = cq  # same source expression as CQ; reuse the calculated array.
    holding_base = 100 * safe_divide(
        close - MyTT.LLV(low, 27), MyTT.HHV(high, 27) - MyTT.LLV(low, 27)
    )
    holding_sma = MyTT.SMA(holding_base, 5, 1)
    holding = 3 * holding_sma - 2 * MyTT.SMA(holding_sma, 3, 1)
    support = MyTT.LLV(holding, 3)
    short_line = MyTT.EMA(safe_divide(close - var2, var3 - var2) * 4, 4) * var1 * 30
    mid_line = MyTT.MA(holding, 12)

    signals = {
        "start": MyTT.CROSS(short_line, mid_line),
        "end": short_line > 90,
        "saturation_hot": (saturation >= 97) & (cq > 90),
        "new_high_breakout": w4 & (MyTT.COUNT(w4, 5) == 1),
        "short_above_mid_long": MyTT.BARSLAST(short_cost < mid_cost) > 30,
        "short_below_mid_long": MyTT.BARSLAST(short_cost > mid_cost) > 30,
    }
    values = {
        "short_cost": short_cost,
        "a": a,
        "x": x,
        "x_with_ref_19": x_with_ref_19,
        "mid_cost": mid_cost,
        "var1": var1,
        "var2": var2,
        "var3": var3,
        "n1": n1,
        "n4": n4,
        "cq": cq,
        "mid_term": mid_term,
        "sat": sat,
        "saturation": saturation,
        "w1": w1.astype(float),
        "w2": w2,
        "w3": w3,
        "w4": w4.astype(float),
        "holding_base": holding_base,
        "holding": holding,
        "support": support,
        "short_line": short_line,
        "mid_line": mid_line,
        "start": np.where(signals["start"], short_line, 0),
        "end": np.where(signals["end"], short_line, 0),
    }
    return build_formula_result(
        formula_id=FORMULA_ID,
        display_name=DISPLAY_NAME,
        minimum_bars=MINIMUM_BARS,
        recommended_bars=RECOMMENDED_BARS,
        frame=frame,
        values=values,
        signals=signals,
    )
