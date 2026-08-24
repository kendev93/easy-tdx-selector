from __future__ import annotations

from pathlib import Path

from selector_app.adapters.easy_tdx_adapter import EasyTdxAdapter


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
