"""Online TDX daily-bar synchronization into the project's DuckDB store."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, cast
from zoneinfo import ZoneInfo

import pandas as pd

from selector_app.market_data.day_format import classify_board, classify_instrument
from selector_app.market_data.models import InstrumentBoard, InstrumentType, MarketCode
from selector_app.market_data.scope import InstrumentScope
from selector_app.market_data.store import DuckDbMarketDataStore
from selector_app.tdx_protocol.client import TdxClient
from selector_app.tdx_protocol.types import KlineCategory, Market

SyncUniverse = Literal["all", "sh", "sz"]
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_LATEST_PROBE_BARS = 2


@dataclass(frozen=True)
class MarketSyncConfig:
    """Configuration for one online-to-DuckDB synchronization run."""

    universe: SyncUniverse = "all"
    bars: int = 800
    timeout: float = 30.0
    instrument_types: tuple[InstrumentType, ...] | None = None
    boards: tuple[InstrumentBoard, ...] | None = None
    prefer_store_targets: bool = False

    def __post_init__(self) -> None:
        if self.universe not in {"all", "sh", "sz"}:
            raise ValueError(f"不支持的同步范围: {self.universe}")
        if not 1 <= self.bars <= 800:
            raise ValueError("每只股票同步的 K 线数量必须在 1 到 800 之间")
        if self.timeout <= 0:
            raise ValueError("行情服务器超时时间必须大于 0")
        if not isinstance(self.prefer_store_targets, bool):
            raise ValueError("行情同步目标来源开关必须是布尔值")
        scope = InstrumentScope.from_values(
            universe=self.universe,
            instrument_types=self.instrument_types,
            boards=self.boards,
        )
        object.__setattr__(self, "instrument_types", scope.instrument_types)
        object.__setattr__(self, "boards", scope.boards)


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
            "source": "online",
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
        market: object,
        code: str,
        category: object,
        start: int,
        count: int,
    ) -> pd.DataFrame: ...


ClientFactory = Callable[[float], TdxMarketClient]
ProgressCallback = Callable[[int, int], None]


def _default_client(timeout: float) -> TdxMarketClient:
    return cast(TdxMarketClient, TdxClient.from_best_host(timeout=timeout))


class TdxMarketSync:
    """Fetch online daily bars and write them only to DuckDB.

    The implementation and client are project-owned; the old class name below
    remains as a compatibility alias for embedders of the first release.
    """

    def __init__(
        self,
        store: DuckDbMarketDataStore | None = None,
        client_factory: ClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store or DuckDbMarketDataStore()
        self._client_factory = client_factory
        self._clock = clock or (lambda: datetime.now(_SHANGHAI_TZ))

    def sync(
        self,
        config: MarketSyncConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> MarketSyncReport:
        failure_reasons: Counter[str] = Counter()
        processed = 0
        updated_files = 0
        unchanged_files = 0
        written_bars = 0
        factory = self._client_factory or _default_client
        with factory(config.timeout) as client:
            targets = self._list_targets(client, config)
            total = len(targets)
            for index, (market, code, instrument_type, board) in enumerate(targets, start=1):
                try:
                    written = self._sync_one(client, market, code, instrument_type, board, config)
                    if written > 0:
                        updated_files += 1
                        written_bars += written
                    else:
                        unchanged_files += 1
                except Exception as exc:  # noqa: BLE001 - isolate one instrument
                    reason = str(exc).strip()[:200] or type(exc).__name__
                    failure_reasons[reason] += 1
                processed += 1
                if progress_callback is not None:
                    progress_callback(processed, total)
        self._store.set_meta("last_online_sync_at", self._clock().isoformat())
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
        config: MarketSyncConfig,
    ) -> list[tuple[MarketCode, str, InstrumentType, InstrumentBoard]]:
        if config.prefer_store_targets:
            stored = self._store.list_instruments(
                market=None if config.universe == "all" else config.universe.upper(),
                instrument_types=config.instrument_types,
                boards=config.boards,
            )
            if stored:
                return [(ref.market, ref.code, ref.instrument_type, ref.board) for ref in stored]
        frame = client.get_security_list_all(pages="all")
        if frame.empty:
            return []
        scope = InstrumentScope.from_values(
            universe=config.universe,
            instrument_types=config.instrument_types,
            boards=config.boards,
        )
        targets: list[tuple[MarketCode, str, InstrumentType, InstrumentBoard]] = []
        seen: set[tuple[MarketCode, str]] = set()
        for row in frame.to_dict(orient="records"):
            market = _to_market(row.get("market"))
            raw_code = str(row.get("code", "")).strip()
            if not raw_code.isdigit() or not 1 <= len(raw_code) <= 6:
                continue
            code = raw_code.zfill(6)
            if market is None:
                continue
            instrument_type = classify_instrument(market, code)
            board = classify_board(market, code)
            if instrument_type is None or board is None:
                continue
            if not scope.matches(market, instrument_type, board):
                continue
            key = (market, code)
            if key not in seen:
                seen.add(key)
                targets.append((key[0], code, instrument_type, board))
        return targets

    def _sync_one(
        self,
        client: TdxMarketClient,
        market: MarketCode,
        code: str,
        instrument_type: InstrumentType,
        board: InstrumentBoard,
        config: MarketSyncConfig,
    ) -> int:
        existing = self._store.read_bars(market, code, include_provisional=True)
        if existing.empty:
            frame = client.get_security_bars(
                _market_enum(market), code, KlineCategory.DAY, 0, config.bars
            )
        else:
            latest = client.get_security_bars(
                _market_enum(market), code, KlineCategory.DAY, 0, _LATEST_PROBE_BARS
            )
            latest_frame = _normalize_online_frame(
                latest,
                market=market,
                code=code,
                instrument_type=instrument_type,
                board=board,
                now=self._clock(),
            )
            if not _has_new_online_data(existing, latest_frame):
                return 0
            frame = client.get_security_bars(
                _market_enum(market), code, KlineCategory.DAY, 0, config.bars
            )
        normalized = _normalize_online_frame(
            frame,
            market=market,
            code=code,
            instrument_type=instrument_type,
            board=board,
            now=self._clock(),
        )
        if normalized.empty:
            return 0
        written, _updated = self._store.upsert_online_bars(normalized)
        return written


def _to_market(value: object) -> MarketCode | None:
    if isinstance(value, Market):
        return "SH" if value is Market.SH else "SZ"
    if isinstance(value, str):
        normalized = value.upper().strip()
        return cast(MarketCode, normalized) if normalized in {"SH", "SZ"} else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        mapping: dict[int, MarketCode] = {0: "SZ", 1: "SH"}
        return mapping.get(int(value))
    name = getattr(value, "name", None)
    if isinstance(name, str) and name.upper() in {"SH", "SZ"}:
        return cast(MarketCode, name.upper())
    return None


def _market_enum(value: MarketCode) -> Market:
    return Market.SH if value == "SH" else Market.SZ


def _normalize_online_frame(
    frame: pd.DataFrame,
    *,
    market: MarketCode,
    code: str,
    instrument_type: InstrumentType,
    board: InstrumentBoard,
    now: datetime,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume", "amount", "bar_status"]
        )
    volume_column = "vol" if "vol" in frame.columns else "volume"
    required = {"open", "high", "low", "close", "amount", volume_column}
    if not required.issubset(frame.columns):
        missing = sorted(required - set(frame.columns))
        raise ValueError(f"在线 K 线响应缺少字段: {', '.join(missing)}")
    dates = pd.to_datetime(
        frame["date"] if "date" in frame.columns else frame.apply(_row_timestamp, axis=1),
        errors="coerce",
    )
    if dates.isna().any():
        raise ValueError("在线 K 线响应包含无效日期")
    current = now if now.tzinfo is not None else now.replace(tzinfo=_SHANGHAI_TZ)
    current = current.astimezone(_SHANGHAI_TZ)
    normalized = pd.DataFrame(
        {
            "date": dates,
            "open": pd.to_numeric(frame["open"], errors="coerce"),
            "high": pd.to_numeric(frame["high"], errors="coerce"),
            "low": pd.to_numeric(frame["low"], errors="coerce"),
            "close": pd.to_numeric(frame["close"], errors="coerce"),
            "volume": pd.to_numeric(frame[volume_column], errors="coerce"),
            "amount": pd.to_numeric(frame["amount"], errors="coerce"),
        }
    )
    if normalized.iloc[:, 1:].isna().any().any():
        raise ValueError("在线 K 线响应包含无效数值")
    normalized["bar_status"] = normalized["date"].map(
        lambda value: (
            "provisional"
            if value.date() == current.date() and (current.hour, current.minute) < (15, 5)
            else "completed"
        )
    )
    normalized["market"] = market
    normalized["code"] = code
    normalized["instrument_type"] = instrument_type
    normalized["board"] = board
    return (
        normalized.sort_values("date", kind="stable")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )


def _row_timestamp(row: pd.Series) -> object:
    if {"year", "month", "day"}.issubset(row.index):
        return pd.Timestamp(year=int(row["year"]), month=int(row["month"]), day=int(row["day"]))
    raise ValueError("在线 K 线响应缺少日期字段")


def _has_new_online_data(existing: pd.DataFrame, latest: pd.DataFrame) -> bool:
    if latest.empty:
        return False
    if existing.empty:
        return True
    existing_by_date = {
        pd.Timestamp(row.date).date(): row for row in existing.itertuples(index=False)
    }
    for row in latest.itertuples(index=False):
        current_date = pd.Timestamp(row.date).date()
        previous = existing_by_date.get(current_date)
        if previous is None:
            return True
        if row.bar_status != previous.bar_status:
            return True
        for column in ("open", "high", "low", "close", "volume", "amount"):
            if float(getattr(row, column)) != float(getattr(previous, column)):
                return True
    return False


EasyTdxMarketSync = TdxMarketSync

__all__ = [
    "EasyTdxMarketSync",
    "MarketSyncConfig",
    "MarketSyncReport",
    "TdxMarketClient",
    "TdxMarketSync",
]
