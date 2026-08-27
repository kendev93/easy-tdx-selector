from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from easy_tdx import SecurityBar
from easy_tdx.offline import append_daily_bars

from selector_app.adapters.easy_tdx_adapter import EasyTdxAdapter, StockRef


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_adapter_lists_only_shenzhen_and_shanghai_a_stock_files(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    for filename in (
        "sh600000.day",
        "sh688001.day",
        "sh510300.day",  # ETF
        "sh000001.day",  # 指数
        "sz000001.day",
        "sz300001.day",
        "sz159919.day",  # ETF
        "sz399001.day",  # 指数
    ):
        touch(vipdoc / ("sh" if filename.startswith("sh") else "sz") / "lday" / filename)

    refs = EasyTdxAdapter().list_stock_refs(str(vipdoc), "all")

    assert [(ref.market, ref.code) for ref in refs] == [
        ("SH", "600000"),
        ("SH", "688001"),
        ("SZ", "000001"),
        ("SZ", "300001"),
    ]


def test_adapter_excludes_provisional_current_day_before_close(tmp_path: Path) -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    filepath = tmp_path / "sh/lday/sh600000.day"
    filepath.parent.mkdir(parents=True)
    append_daily_bars(
        filepath,
        [
            SecurityBar(10, 10.2, 10.4, 9.8, 100_000, 1_000_000, 2026, 8, 25, 0, 0),
            SecurityBar(10.2, 10.5, 10.6, 10.0, 110_000, 1_100_000, 2026, 8, 26, 0, 0),
        ],
        price_coeff=0.01,
        vol_coeff=0.01,
    )
    ref = StockRef(market="SH", code="600000", path=filepath)

    before_close = EasyTdxAdapter(
        clock=lambda: datetime(2026, 8, 26, 10, 0, tzinfo=timezone),
    ).read_stock(ref)
    after_close = EasyTdxAdapter(
        clock=lambda: datetime(2026, 8, 26, 16, 0, tzinfo=timezone),
    ).read_stock(ref)

    assert before_close["date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-08-25"]
    assert after_close["date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-08-25",
        "2026-08-26",
    ]


def test_adapter_builds_a_valid_single_stock_reference(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    vipdoc.mkdir()

    ref = EasyTdxAdapter().stock_ref(vipdoc, "SH", "600000")

    assert ref.market == "SH"
    assert ref.code == "600000"
    assert ref.path == vipdoc / "sh/lday/sh600000.day"
