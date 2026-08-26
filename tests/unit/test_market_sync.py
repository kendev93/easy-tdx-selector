from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from easy_tdx import KlineCategory, Market, SecurityBar
from easy_tdx.offline import append_daily_bars, read_daily_bars

from selector_app.adapters.market_sync import EasyTdxMarketSync, MarketSyncConfig


def bars_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-20", "2026-08-21", "2026-08-22"]),
            "open": [10.0, 10.2, 10.3],
            "high": [10.4, 10.5, 10.6],
            "low": [9.8, 10.0, 10.1],
            "close": [10.2, 10.3, 10.5],
            "vol": [100_000.0, 110_000.0, 120_000.0],
            "amount": [1_000_000.0, 1_100_000.0, 1_200_000.0],
        }
    )


class FakeClient:
    def __init__(self, *, fail_code: str | None = None, frame: pd.DataFrame | None = None) -> None:
        self.fail_code = fail_code
        self.frame = frame
        self.requests: list[tuple[str, int]] = []

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get_security_list_all(self, pages: str = "all") -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"market": Market.SH, "code": "600000"},
                {"market": Market.SZ, "code": "000001"},
                {"market": Market.SH, "code": "510300"},  # defensive fund filter
            ]
        )

    def get_security_bars(
        self, market: Market, code: str, category: KlineCategory, start: int, count: int
    ) -> pd.DataFrame:
        assert category == KlineCategory.DAY
        assert start == 0
        self.requests.append((code, count))
        if code == self.fail_code:
            raise RuntimeError("upstream unavailable")
        source = self.frame if self.frame is not None else bars_frame()
        return source.tail(min(count, len(source)))


def test_sync_writes_tdx_day_files_and_skips_non_stock_codes(tmp_path: Path) -> None:
    service = EasyTdxMarketSync(client_factory=lambda _timeout: FakeClient())
    report = service.sync(MarketSyncConfig(vipdoc_path=tmp_path))

    assert report.total_candidates == 2
    assert report.processed == 2
    assert report.updated_files == 2
    assert report.written_bars == 6
    assert report.errors == 0
    assert len(read_daily_bars(tmp_path / "sh/lday/sh600000.day")) == 3
    assert len(read_daily_bars(tmp_path / "sz/lday/sz000001.day")) == 3
    assert not (tmp_path / "sh/lday/sh510300.day").exists()


def test_sync_continues_after_one_upstream_failure(tmp_path: Path) -> None:
    service = EasyTdxMarketSync(client_factory=lambda _timeout: FakeClient(fail_code="000001"))
    report = service.sync(MarketSyncConfig(vipdoc_path=tmp_path))

    assert report.processed == 2
    assert report.updated_files == 1
    assert report.written_bars == 3
    assert report.errors == 1
    assert report.failure_reasons["upstream unavailable"] == 1


def test_sync_does_not_duplicate_existing_day_records(tmp_path: Path) -> None:
    client = FakeClient()
    service = EasyTdxMarketSync(client_factory=lambda _timeout: client)
    config = MarketSyncConfig(vipdoc_path=tmp_path)

    first = service.sync(config)
    second = service.sync(config)

    assert first.written_bars == 6
    assert second.written_bars == 0
    assert client.requests.count(("600000", 800)) == 1
    assert client.requests.count(("000001", 800)) == 1
    assert client.requests.count(("600000", 2)) == 1
    assert client.requests.count(("000001", 2)) == 1
    assert len(read_daily_bars(tmp_path / "sh/lday/sh600000.day")) == 3


def test_sync_finds_the_last_completed_bar_before_close(tmp_path: Path) -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    morning = datetime(2026, 8, 26, 10, 0, tzinfo=timezone)
    server_frame = bars_frame().copy()
    server_frame.loc[server_frame.index[-1], "date"] = pd.Timestamp("2026-08-26")

    class SingleStockClient(FakeClient):
        def get_security_list_all(self, pages: str = "all") -> pd.DataFrame:
            return pd.DataFrame([{"market": Market.SH, "code": "600000"}])

    client = SingleStockClient(frame=server_frame)
    filepath = tmp_path / "sh/lday/sh600000.day"
    filepath.parent.mkdir(parents=True)
    append_daily_bars(
        filepath,
        [
            SecurityBar(
                open=10.0,
                close=10.2,
                high=10.4,
                low=9.8,
                vol=100_000,
                amount=1_000_000,
                year=2026,
                month=8,
                day=20,
                hour=0,
                minute=0,
            )
        ],
        price_coeff=0.01,
        vol_coeff=0.01,
    )

    report = EasyTdxMarketSync(
        client_factory=lambda _timeout: client,
        clock=lambda: morning,
    ).sync(MarketSyncConfig(vipdoc_path=tmp_path))

    assert report.written_bars == 1
    assert client.requests == [("600000", 2), ("600000", 800)]
    assert [bar.day for bar in read_daily_bars(filepath)] == [20, 21]


def test_sync_replaces_partial_current_day_record_after_market_close(tmp_path: Path) -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    close_time = datetime(2026, 8, 26, 16, 0, tzinfo=timezone)
    current_day = pd.Timestamp("2026-08-26")
    server_frame = bars_frame().copy()
    server_frame.loc[server_frame.index[-1], "date"] = current_day

    class SingleStockClient(FakeClient):
        def get_security_list_all(self, pages: str = "all") -> pd.DataFrame:
            return pd.DataFrame([{"market": Market.SH, "code": "600000"}])

    client = SingleStockClient(frame=server_frame)
    filepath = tmp_path / "sh/lday/sh600000.day"
    filepath.parent.mkdir(parents=True)
    append_daily_bars(
        filepath,
        [
            SecurityBar(
                open=9.0,
                close=9.5,
                high=10.0,
                low=8.5,
                vol=100_000,
                amount=950_000,
                year=2026,
                month=8,
                day=26,
                hour=0,
                minute=0,
            )
        ],
        price_coeff=0.01,
        vol_coeff=0.01,
    )
    service = EasyTdxMarketSync(
        client_factory=lambda _timeout: client,
        clock=lambda: close_time,
    )

    report = service.sync(MarketSyncConfig(vipdoc_path=tmp_path))

    assert report.updated_files == 1
    assert report.written_bars == 1
    assert read_daily_bars(filepath)[-1].close == 10.5
