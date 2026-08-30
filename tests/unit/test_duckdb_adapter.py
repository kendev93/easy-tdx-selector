from __future__ import annotations

from pathlib import Path

import pandas as pd

from selector_app.market_data.adapter import DuckDbMarketDataAdapter
from selector_app.market_data.store import DuckDbMarketDataStore


def _frame(instrument_type: str = "stock") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")],
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.5, 11.5],
            "volume": [1000.0, 1100.0],
            "amount": [10500.0, 12650.0],
            "bar_status": ["completed", "completed"],
            "instrument_type": [instrument_type, instrument_type],
        }
    )


def test_duckdb_adapter_lists_and_reads_instruments_without_vipdoc(tmp_path: Path) -> None:
    store = DuckDbMarketDataStore(tmp_path / "market.duckdb")
    store.replace_local_bars("SH", "600000", "stock", _frame())
    store.replace_local_bars("SH", "510300", "fund", _frame("fund"))
    adapter = DuckDbMarketDataAdapter(store)

    refs = adapter.list_stock_refs("/unused", "all")
    ref = adapter.stock_ref("/unused", "SH", "510300")

    assert [(item.market, item.code, item.instrument_type) for item in refs] == [
        ("SH", "510300", "fund"),
        ("SH", "600000", "stock"),
    ]
    assert ref.path == Path("/unused")
    assert ref.instrument_type == "fund"
    assert list(adapter.read_stock(ref)["close"]) == [10.5, 11.5]


def test_duckdb_adapter_custom_universe_uses_codes_from_file(tmp_path: Path) -> None:
    store = DuckDbMarketDataStore(tmp_path / "market.duckdb")
    store.replace_local_bars("SH", "600000", "stock", _frame())
    store.replace_local_bars("SH", "510300", "fund", _frame("fund"))
    universe = tmp_path / "universe.txt"
    universe.write_text("SH 600000\nSH 510300\n", encoding="utf-8")
    adapter = DuckDbMarketDataAdapter(store)

    refs = adapter.list_stock_refs("/unused", "custom", universe)

    assert [(item.market, item.code) for item in refs] == [("SH", "600000"), ("SH", "510300")]
