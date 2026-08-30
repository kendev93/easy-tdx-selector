from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from selector_app.backtest.engine import SignalBacktestConfig, run_signal_backtest


def _frame() -> pd.DataFrame:
    close = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 13.0])
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(close), freq="D"),
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000.0,
            "amount": close * 1000,
        }
    )


def test_signal_engine_executes_on_next_bar_and_tracks_full_position() -> None:
    result = run_signal_backtest(
        _frame(),
        np.array([False, True, False, False, False, False]),
        np.array([False, False, False, False, True, False]),
        SignalBacktestConfig(initial_cash=10_000, commission=0, min_commission=0, stamp_tax=0),
    )

    assert result.trades["direction"].tolist() == ["BUY", "SELL"]
    assert result.trades["datetime"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-01-03",
        "2024-01-06",
    ]
    assert result.performance["end_value"] == 10_800.0
    assert result.equity_curve.iloc[0]["date"] == "2024-01-01"


def test_signal_engine_supports_fixed_size_and_date_window() -> None:
    result = run_signal_backtest(
        _frame(),
        np.array([False, True, False, False, False, False]),
        np.array([False, False, False, False, True, False]),
        SignalBacktestConfig(
            initial_cash=10_000,
            commission=0,
            min_commission=0,
            stamp_tax=0,
            position_mode="fixed",
            fixed_size=200,
            lot_size=100,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 5),
        ),
    )

    assert result.trades.iloc[0]["size"] == 200
    assert len(result.equity_curve) == 4
