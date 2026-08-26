"""Online TDX market-data synchronizer for the shared ``vipdoc`` directory.

All upstream imports and format conversion live here.  The rest of the app sees
only ``MarketSyncConfig`` and ``MarketSyncReport``.  A sync probes one latest bar
per existing file first; a full 800-bar request is made only when the server has
new completed data, preventing repeated bulk downloads on every sync.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Literal, Protocol, cast
from zoneinfo import ZoneInfo

import pandas as pd
from easy_tdx import KlineCategory, Market, SecurityBar, TdxClient
from easy_tdx.offline import (
    encode_daily_bar,
    find_daily_bar_file,
    get_last_bar_date,
    sync_daily_bars_from_security_bars,
)

from .easy_tdx_adapter import MarketCode, is_supported_a_stock

logger = logging.getLogger(__name__)

SyncUniverse = Literal["all", "sh", "sz"]
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_MARKET_PRICE_COEFFICIENT = 0.01
_MARKET_VOLUME_COEFFICIENT = 0.01
_LATEST_PROBE_BARS = 2


@dataclass(frozen=True)
class MarketSyncConfig:
    """Config for one online-to-vipdoc synchronization run."""

    vipdoc_path: str | Path = "/data/vipdoc"
    universe: SyncUniverse = "all"
    bars: int = 800
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if self.universe not in {"all", "sh", "sz"}:
            raise ValueError(f"不支持的同步范围: {self.universe}")
        if not 1 <= self.bars <= 800:
            raise ValueError("每只股票同步的 K 线数量必须在 1 到 800 之间")
        if self.timeout <= 0:
            raise ValueError("行情服务器超时时间必须大于 0")

    @property
    def root(self) -> Path:
        return Path(self.vipdoc_path).expanduser()


@dataclass(frozen=True)
class MarketSyncReport:
    total_candidates: int
    processed: int
    updated_files: int
    unchanged_files: int
    written_bars: int
    errors: int
    failure_reasons: Mapping[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "total_candidates": self.total_candidates,
            "processed": self.processed,
            "updated_files": self.updated_files,
            "unchanged_files": self.unchanged_files,
            "written_bars": self.written_bars,
            "errors": self.errors,
            "failure_reasons": dict(self.failure_reasons),
        }


class TdxMarketClient(Protocol):
    def __enter__(self) -> TdxMarketClient: ...

    def __exit__(self, *args: object) -> None: ...

    def get_security_list_all(self, pages: str = "all") -> pd.DataFrame: ...

    def get_security_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int,
    ) -> pd.DataFrame: ...


ClientFactory = Callable[[float], TdxMarketClient]
ProgressCallback = Callable[[int, int], None]


class EasyTdxMarketSync:
    """Fetch completed daily bars and append them in TDX ``.day`` format."""

    def __init__(
        self,
        client_factory: ClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._clock = clock or (lambda: datetime.now(_SHANGHAI_TZ))
        self._write_lock = Lock()

    def sync(
        self,
        config: MarketSyncConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> MarketSyncReport:
        root = config.root
        if not root.is_dir():
            raise ValueError(f"vipdoc 目录不存在或不是目录: {root}")

        failure_reasons: Counter[str] = Counter()
        processed = 0
        updated_files = 0
        unchanged_files = 0
        written_bars = 0

        factory = self._client_factory or (
            lambda timeout: TdxClient.from_best_host(timeout=timeout)
        )
        with factory(config.timeout) as client:
            targets = self._list_targets(client, config.universe)
            total = len(targets)
            for index, (market, code) in enumerate(targets, start=1):
                try:
                    written = self._sync_one(client, market, code, config)
                    if written > 0:
                        updated_files += 1
                        written_bars += written
                    else:
                        unchanged_files += 1
                except Exception as exc:  # noqa: BLE001 - isolate one security
                    reason = str(exc) or type(exc).__name__
                    failure_reasons[reason] += 1
                    logger.warning("行情同步失败 %s%s: %s", market.name, code, reason)
                processed += 1
                if progress_callback is not None:
                    progress_callback(processed, total)

        return MarketSyncReport(
            total_candidates=total,
            processed=processed,
            updated_files=updated_files,
            unchanged_files=unchanged_files,
            written_bars=written_bars,
            errors=sum(failure_reasons.values()),
            failure_reasons=dict(failure_reasons),
        )

    def _list_targets(
        self,
        client: TdxMarketClient,
        universe: SyncUniverse,
    ) -> list[tuple[Market, str]]:
        frame = client.get_security_list_all(pages="all")
        if frame.empty:
            return []
        allowed_markets = {
            "all": {Market.SH, Market.SZ},
            "sh": {Market.SH},
            "sz": {Market.SZ},
        }[universe]
        targets: list[tuple[Market, str]] = []
        seen: set[tuple[Market, str]] = set()
        for row in frame.to_dict(orient="records"):
            market = _to_market(row.get("market"))
            code = str(row.get("code", "")).strip().zfill(6)
            if market not in allowed_markets:
                continue
            market_code: MarketCode = "SH" if market == Market.SH else "SZ"
            if not is_supported_a_stock(market_code, code):
                continue
            target = (market, code)
            if target not in seen:
                seen.add(target)
                targets.append(target)
        return targets

    def _sync_one(
        self,
        client: TdxMarketClient,
        market: Market,
        code: str,
        config: MarketSyncConfig,
    ) -> int:
        filepath = find_daily_bar_file(market, code, config.root)
        _ensure_safe_target(config.root, filepath)
        last_date = get_last_bar_date(filepath)

        if last_date is None:
            frame = client.get_security_bars(market, code, KlineCategory.DAY, 0, config.bars)
        else:
            # Before the close, the newest server row can be today's provisional
            # bar. Fetch one extra row so yesterday's completed bar is still
            # discoverable and missing data is not left behind until tomorrow.
            latest = client.get_security_bars(
                market,
                code,
                KlineCategory.DAY,
                0,
                _LATEST_PROBE_BARS,
            )
            latest_bars = _dataframe_to_completed_bars(latest, now=self._clock())
            if not latest_bars or _bar_date_int(latest_bars[-1]) <= last_date:
                if (
                    latest_bars
                    and _is_current_day_after_close(latest_bars[-1], now=self._clock())
                    and _bar_date_int(latest_bars[-1]) == last_date
                ):
                    return self._replace_last_bar(filepath, latest_bars[-1])
                return 0
            frame = client.get_security_bars(market, code, KlineCategory.DAY, 0, config.bars)

        bars = _dataframe_to_completed_bars(frame, now=self._clock())
        if not bars:
            return 0
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock:
            written = sync_daily_bars_from_security_bars(
                filepath,
                bars,
                price_coeff=_MARKET_PRICE_COEFFICIENT,
                vol_coeff=_MARKET_VOLUME_COEFFICIENT,
            )
        return cast(int, written)

    def _replace_last_bar(self, filepath: Path, bar: SecurityBar) -> int:
        """Replace a same-day provisional bar with the completed close."""

        with self._write_lock:
            # The public writer repairs a possible partial tail before the raw
            # fixed-size replacement below; it receives no new bars by design.
            sync_daily_bars_from_security_bars(
                filepath,
                [],
                price_coeff=_MARKET_PRICE_COEFFICIENT,
                vol_coeff=_MARKET_VOLUME_COEFFICIENT,
            )
            encoded = encode_daily_bar(
                bar,
                price_coeff=_MARKET_PRICE_COEFFICIENT,
                vol_coeff=_MARKET_VOLUME_COEFFICIENT,
            )
            with filepath.open("r+b") as handle:
                handle.seek(-len(encoded), os.SEEK_END)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        return 1


def _to_market(value: object) -> Market | None:
    if isinstance(value, Market):
        return value if value in {Market.SH, Market.SZ} else None
    if isinstance(value, str):
        normalized = value.upper().strip()
        if normalized == "SH":
            return Market.SH
        if normalized == "SZ":
            return Market.SZ
    if not isinstance(value, (int, float)):
        return None
    try:
        market = Market(int(value))
    except (ValueError, OverflowError):
        return None
    return market if market in {Market.SH, Market.SZ} else None


def _dataframe_to_completed_bars(
    frame: pd.DataFrame,
    *,
    now: datetime | None = None,
) -> list[SecurityBar]:
    if frame.empty:
        return []
    volume_column = "vol" if "vol" in frame.columns else "volume"
    required = {"open", "high", "low", "close", "amount", volume_column}
    if not required.issubset(frame.columns):
        missing = sorted(required - set(frame.columns))
        raise ValueError(f"在线 K 线响应缺少字段: {', '.join(missing)}")
    bars: list[SecurityBar] = []
    for row in frame.to_dict(orient="records"):
        timestamp = _row_timestamp(row)
        if _is_unfinished_today(timestamp, now=now):
            continue
        bars.append(
            SecurityBar(
                open=float(row["open"]),
                close=float(row["close"]),
                high=float(row["high"]),
                low=float(row["low"]),
                vol=float(row[volume_column]),
                amount=float(row["amount"]),
                year=timestamp.year,
                month=timestamp.month,
                day=timestamp.day,
                hour=0,
                minute=0,
            )
        )
    return sorted(bars, key=_bar_date_int)


def _row_timestamp(row: Mapping[str, object]) -> pd.Timestamp:
    if "date" in row:
        return pd.Timestamp(row["date"])
    if {"year", "month", "day"}.issubset(row):
        return pd.Timestamp(
            year=_as_int(row["year"]),
            month=_as_int(row["month"]),
            day=_as_int(row["day"]),
        )
    raise ValueError("在线 K 线响应缺少日期字段")


def _is_unfinished_today(timestamp: pd.Timestamp, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(_SHANGHAI_TZ)
    return timestamp.date() == current.date() and (current.hour, current.minute) < (15, 5)


def _is_current_day_after_close(bar: SecurityBar, *, now: datetime) -> bool:
    timestamp = pd.Timestamp(year=bar.year, month=bar.month, day=bar.day)
    return timestamp.date() == now.date() and not _is_unfinished_today(timestamp, now=now)


def _bar_date_int(bar: SecurityBar) -> int:
    return (
        int(cast(int, bar.year)) * 10000 + int(cast(int, bar.month)) * 100 + int(cast(int, bar.day))
    )


def _as_int(value: object) -> int:
    if isinstance(value, (int, float, str)):
        return int(value)
    raise ValueError("在线 K 线日期字段类型无效")


def _ensure_safe_target(root: Path, filepath: Path) -> None:
    root_resolved = root.resolve()
    target_resolved = filepath.resolve()
    if not target_resolved.is_relative_to(root_resolved):
        raise ValueError("行情文件路径超出 vipdoc 目录范围")
