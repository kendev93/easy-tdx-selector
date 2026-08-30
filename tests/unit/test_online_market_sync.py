from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from selector_app.adapters.market_sync import EasyTdxMarketSync, MarketSyncConfig
from selector_app.market_data.store import DuckDbMarketDataStore
from selector_app.tdx_protocol.types import KlineCategory


def _frame(close: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-20", "2026-08-21", "2026-08-22"]),
            "open": [close, close + 0.1, close + 0.2],
            "high": [close + 0.2, close + 0.3, close + 0.4],
            "low": [close - 0.2, close - 0.1, close],
            "close": [close + 0.1, close + 0.2, close + 0.4],
            "volume": [1000.0, 1100.0, 1200.0],
            "amount": [10000.0, 11000.0, 12000.0],
            "bar_status": ["completed", "completed", "completed"],
        }
    )


class FakeClient:
    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        self.frame = frame if frame is not None else _frame()
        self.requests: list[tuple[str, int]] = []

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get_security_list_all(self, pages: str = "all") -> pd.DataFrame:
        del pages
        return pd.DataFrame(
            [
                {"market": "SH", "code": "600000"},
                {"market": "SH", "code": "510300"},
                {"market": "SH", "code": "000001"},
            ]
        )

    def get_security_bars(
        self, market: str, code: str, category: str, start: int, count: int
    ) -> pd.DataFrame:
        assert category == KlineCategory.DAY
        assert start == 0
        self.requests.append((code, count))
        return self.frame.tail(min(count, len(self.frame))).copy()


def test_online_sync_writes_duckdb_without_touching_vipdoc(tmp_path: Path) -> None:
    store = DuckDbMarketDataStore(tmp_path / "market.duckdb")
    source_dir = tmp_path / "vipdoc"
    source_dir.mkdir()
    client = FakeClient()

    report = EasyTdxMarketSync(
        store=store,
        client_factory=lambda _timeout: client,
        clock=lambda: datetime(2026, 8, 30, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    ).sync(MarketSyncConfig(universe="all"))

    assert report.total_candidates == 3
    assert report.processed == 3
    assert report.updated_files == 3
    assert report.written_bars == 9
    assert store.status().bar_count == 9
    assert not list(source_dir.rglob("*.day"))


def test_online_sync_does_not_overwrite_local_rows(tmp_path: Path) -> None:
    store = DuckDbMarketDataStore(tmp_path / "market.duckdb")
    local = _frame(20.0)
    store.replace_local_bars("SH", "600000", "stock", local)
    client = FakeClient(_frame(99.0))

    report = EasyTdxMarketSync(
        store=store,
        client_factory=lambda _timeout: client,
    ).sync(MarketSyncConfig(universe="sh"))

    assert report.written_bars == 6
    frame = store.read_bars("SH", "600000")
    assert frame.iloc[0]["close"] == 20.1
    assert set(frame.loc[frame["code"] == "600000", "source"]) == {"local"}
