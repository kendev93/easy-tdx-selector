from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from selector_app.adapters.market_sync import EasyTdxMarketSync, MarketSyncConfig
from selector_app.market_data.store import DuckDbMarketDataStore
from selector_app.tdx_protocol.types import KlineCategory


def bars_frame(close: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-20", "2026-08-21", "2026-08-22"]),
            "open": [close, close + 0.1, close + 0.2],
            "high": [close + 0.4, close + 0.5, close + 0.6],
            "low": [close - 0.2, close - 0.1, close],
            "close": [close + 0.2, close + 0.3, close + 0.5],
            "vol": [100_000.0, 110_000.0, 120_000.0],
            "amount": [1_000_000.0, 1_100_000.0, 1_200_000.0],
        }
    )


class FakeClient:
    def __init__(self, *, fail_code: str | None = None, frame: pd.DataFrame | None = None) -> None:
        self.fail_code = fail_code
        self.frame = frame if frame is not None else bars_frame()
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
                {"market": "SZ", "code": "000001"},
                {"market": "SH", "code": "510300"},
            ]
        )

    def get_security_bars(
        self, market: object, code: str, category: object, start: int, count: int
    ) -> pd.DataFrame:
        del market
        assert category == KlineCategory.DAY
        assert start == 0
        self.requests.append((code, count))
        if code == self.fail_code:
            raise RuntimeError("upstream unavailable")
        return self.frame.tail(min(count, len(self.frame))).copy()


def _service(
    tmp_path: Path, client: FakeClient, *, clock: datetime | None = None
) -> EasyTdxMarketSync:
    return EasyTdxMarketSync(
        store=DuckDbMarketDataStore(tmp_path / "market.duckdb"),
        client_factory=lambda _timeout: client,
        clock=(lambda: clock) if clock is not None else None,
    )


def test_sync_writes_all_known_instruments_to_duckdb(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeClient())

    report = service.sync(MarketSyncConfig())

    assert report.total_candidates == 3
    assert report.processed == 3
    assert report.updated_files == 3
    assert report.written_bars == 9
    assert report.errors == 0
    assert service._store.status().bar_count == 9


def test_sync_continues_after_one_upstream_failure(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeClient(fail_code="000001"))

    report = service.sync(MarketSyncConfig())

    assert report.processed == 3
    assert report.updated_files == 2
    assert report.written_bars == 6
    assert report.errors == 1
    assert report.failure_reasons["upstream unavailable"] == 1


def test_sync_skips_unchanged_online_rows(tmp_path: Path) -> None:
    client = FakeClient()
    service = _service(tmp_path, client)

    first = service.sync(MarketSyncConfig())
    second = service.sync(MarketSyncConfig())

    assert first.written_bars == 9
    assert second.written_bars == 0
    assert second.unchanged_files == 3
    assert client.requests.count(("600000", 800)) == 1
    assert client.requests.count(("600000", 2)) == 1


def test_sync_uses_completed_bar_after_close(tmp_path: Path) -> None:
    current_day = pd.Timestamp("2026-08-26")
    frame = bars_frame()
    frame.loc[frame.index[-1], "date"] = current_day
    client = FakeClient(frame=frame)
    service = _service(
        tmp_path,
        client,
        clock=datetime(2026, 8, 26, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    report = service.sync(MarketSyncConfig(universe="sh"))

    assert report.written_bars == 6
    assert service._store.read_bars("SH", "600000").iloc[-1]["date"] == pd.Timestamp("2026-08-26")
