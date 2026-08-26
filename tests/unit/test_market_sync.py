from __future__ import annotations

from pathlib import Path

import pandas as pd
from easy_tdx import KlineCategory, Market
from easy_tdx.offline import read_daily_bars

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
    def __init__(self, *, fail_code: str | None = None) -> None:
        self.fail_code = fail_code
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
        return bars_frame().tail(1) if count == 1 else bars_frame()


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
    assert client.requests.count(("600000", 1)) == 1
    assert client.requests.count(("000001", 1)) == 1
    assert len(read_daily_bars(tmp_path / "sh/lday/sh600000.day")) == 3
