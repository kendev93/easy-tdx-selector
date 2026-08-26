"""The single integration boundary to the upstream ``easy_tdx`` package.

Business code consumes ``StockRef`` and normalized pandas frames from this module
and never imports easy_tdx internals directly.  The adapter intentionally limits
offline universe discovery to Shanghai/Shenzhen A-share stock code ranges so
funds, ETFs, indices, bonds, and unsupported Beijing files are not silently
treated as stocks.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd

# These are public upstream APIs: no easy_tdx.* private module is imported here.
from easy_tdx import Market, SecurityBar
from easy_tdx.offline import find_daily_bar_file, read_daily_bars, resolve_vipdoc

MarketCode = Literal["SH", "SZ"]

_CODE_PATTERN = re.compile(r"^\d{6}$")
_MARKET_PATTERN = re.compile(r"^(SH|SZ)[:\s-]?([0-9]{6})$", re.IGNORECASE)


def suggested_vipdoc_path() -> str:
    """Suggest a usable path for the UI without requiring a manual first entry."""

    configured = os.getenv("SELECTOR_VIPDOC_PATH")
    if configured:
        return str(Path(configured).expanduser())
    container_path = Path("/data/vipdoc")
    if container_path.is_dir():
        return str(container_path)
    try:
        return str(resolve_vipdoc(None))
    except Exception:  # noqa: BLE001 - suggestion must never block metadata
        return "/data/vipdoc"


@dataclass(frozen=True)
class StockRef:
    """A stable reference to one offline A-share daily data file."""

    market: MarketCode
    code: str
    path: Path


class MarketDataAdapter(Protocol):
    def list_stock_refs(
        self,
        vipdoc_path: str | Path,
        universe: str,
        universe_file: str | Path | None = None,
    ) -> list[StockRef]: ...

    def read_stock(self, ref: StockRef) -> pd.DataFrame: ...


def _market_to_upstream(market: MarketCode) -> Market:
    return Market.SH if market == "SH" else Market.SZ


def is_supported_a_stock(market: MarketCode, code: str) -> bool:
    """Return whether a code is an SH/SZ A-share stock, not a fund/index/bond."""

    if not _CODE_PATTERN.fullmatch(code):
        return False
    if market == "SH":
        return code.startswith(("60", "68"))
    return code.startswith(("00", "30"))


def _parse_universe_line(line: str) -> tuple[MarketCode, str] | None:
    normalized = line.split("#", 1)[0].strip()
    if not normalized:
        return None
    match = _MARKET_PATTERN.fullmatch(normalized)
    if match:
        parsed_market: MarketCode = "SH" if match.group(1).upper() == "SH" else "SZ"
        code = match.group(2)
        return parsed_market, code
    if _CODE_PATTERN.fullmatch(normalized):
        market: MarketCode = "SH" if normalized.startswith(("6", "9")) else "SZ"
        return market, normalized
    raise ValueError(f"自定义股票列表中的格式无效: {line.strip()}")


def _frame_from_bars(bars: list[SecurityBar]) -> pd.DataFrame:
    """Convert public ``SecurityBar`` dataclasses into an app-owned frame."""

    rows = [
        {
            "date": pd.Timestamp(
                year=int(bar.year),
                month=int(bar.month),
                day=int(bar.day),
            ),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.vol),
            "amount": float(bar.amount),
        }
        for bar in bars
    ]
    return pd.DataFrame(
        rows,
        columns=["date", "open", "high", "low", "close", "volume", "amount"],
    )


class EasyTdxAdapter:
    """Read normalized daily bars and stock references through easy_tdx."""

    def resolve_vipdoc(self, vipdoc_path: str | Path | None) -> Path:
        normalized = Path(vipdoc_path).expanduser() if vipdoc_path is not None else None
        return Path(resolve_vipdoc(normalized))

    def list_stock_refs(
        self,
        vipdoc_path: str | Path,
        universe: str,
        universe_file: str | Path | None = None,
    ) -> list[StockRef]:
        vipdoc = self.resolve_vipdoc(vipdoc_path)
        if universe == "custom":
            if universe_file is None:
                raise ValueError("自定义股票范围必须提供股票列表文件")
            return self._list_custom_refs(vipdoc, Path(universe_file).expanduser())

        markets: tuple[MarketCode, ...]
        if universe == "sh":
            markets = ("SH",)
        elif universe == "sz":
            markets = ("SZ",)
        elif universe == "all":
            markets = ("SH", "SZ")
        else:
            raise ValueError(f"不支持的扫描范围: {universe}")

        refs: list[StockRef] = []
        for market in markets:
            exchange = market.lower()
            for path in sorted((vipdoc / exchange / "lday").glob(f"{exchange}??????.day")):
                code = path.stem[2:]
                if is_supported_a_stock(market, code):
                    refs.append(StockRef(market=market, code=code, path=path))
        return refs

    def _list_custom_refs(self, vipdoc: Path, universe_file: Path) -> list[StockRef]:
        if not universe_file.is_file():
            raise ValueError(f"自定义股票列表文件不存在: {universe_file}")
        refs: list[StockRef] = []
        seen: set[tuple[MarketCode, str]] = set()
        for line in universe_file.read_text(encoding="utf-8").splitlines():
            parsed = _parse_universe_line(line)
            if parsed is None:
                continue
            market, code = parsed
            if not is_supported_a_stock(market, code):
                continue
            key = (market, code)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                StockRef(
                    market=market,
                    code=code,
                    path=find_daily_bar_file(_market_to_upstream(market), code, vipdoc),
                )
            )
        return refs

    def read_stock(self, ref: StockRef) -> pd.DataFrame:
        """Read one stock without exposing the upstream ``SecurityBar`` type."""

        bars = read_daily_bars(ref.path)
        frame = _frame_from_bars(bars)
        if frame.empty:
            return frame
        return frame.sort_values("date", kind="stable").reset_index(drop=True)
