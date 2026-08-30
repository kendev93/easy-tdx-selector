"""Incremental local ``.day`` to DuckDB ingestion."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .day_format import (
    DayFileError,
    classify_board,
    classify_instrument,
    discover_day_files,
    read_day_file,
)
from .models import ImportReport, InstrumentBoard, InstrumentType
from .scope import InstrumentScope
from .store import DuckDbMarketDataStore

ProgressCallback = Callable[[int, int], None]
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalDayImporter:
    """Import local files without ever writing to the user's vipdoc tree."""

    def __init__(
        self,
        store: DuckDbMarketDataStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(_SHANGHAI_TZ))

    def import_vipdoc(
        self,
        vipdoc_path: str | Path,
        *,
        universe: str = "all",
        instrument_types: Iterable[InstrumentType] | None = None,
        boards: Iterable[InstrumentBoard] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ImportReport:
        root = Path(vipdoc_path).expanduser().resolve()
        files = discover_day_files(root, universe)
        normalized_universe = universe.strip().lower()
        scanned_markets = {"sh", "sz"} if normalized_universe == "all" else {normalized_universe}
        scope = InstrumentScope.from_values(
            universe=universe,
            instrument_types=instrument_types,
            boards=boards,
        )
        previous = {str(item["relative_path"]): item for item in self._store.source_files(root)}
        failure_reasons: Counter[str] = Counter()
        imported_files = 0
        updated_files = 0
        unchanged_files = 0
        skipped_files = 0
        filtered_files = 0
        imported_instruments = 0
        replaced_instruments = 0
        imported_bars = 0
        provisional_bars = 0
        errors = 0
        seen: set[str] = set()

        for index, path in enumerate(files, start=1):
            relative_path = path.relative_to(root).as_posix()
            seen.add(relative_path)
            market = path.name[:2].upper()
            code = path.stem[2:]
            instrument_type = classify_instrument(market, code)
            stat = path.stat()
            board = classify_board(market, code)
            if instrument_type is None or board is None:
                skipped_files += 1
                failure_reasons["unknown_instrument"] += 1
                self._store.record_source_file(
                    source_root=root,
                    relative_path=relative_path,
                    market=market,
                    code=code,
                    instrument_type=None,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=None,
                    status="skipped",
                    error="unknown_instrument",
                )
                self._report_progress(progress_callback, index, len(files))
                continue
            if not scope.matches(market, instrument_type, board):
                skipped_files += 1
                filtered_files += 1
                failure_reasons["scope_filtered"] += 1
                self._report_progress(progress_callback, index, len(files))
                continue

            old = previous.get(relative_path)
            current = self._clock()
            after_market_close = (current.hour, current.minute) >= (15, 5)
            needs_finalize = (
                old is not None
                and after_market_close
                and self._store.has_provisional_bars(market, code)
            )
            if (
                old is not None
                and old["status"] == "imported"
                and int(str(old["size"])) == stat.st_size
                and int(str(old["mtime_ns"])) == stat.st_mtime_ns
                and not needs_finalize
            ):
                unchanged_files += 1
                self._report_progress(progress_callback, index, len(files))
                continue

            checksum = _sha256(path)
            if (
                old is not None
                and old.get("sha256") == checksum
                and old["status"] == "imported"
                and not needs_finalize
            ):
                unchanged_files += 1
                self._store.record_source_file(
                    source_root=root,
                    relative_path=relative_path,
                    market=market,
                    code=code,
                    instrument_type=instrument_type,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=checksum,
                    status="imported",
                )
                self._report_progress(progress_callback, index, len(files))
                continue

            try:
                parsed = read_day_file(path, now=current)
                if parsed.frame.empty:
                    raise DayFileError("日线文件没有完整记录")
                count = self._store.replace_local_bars(
                    market,
                    code,
                    instrument_type,
                    parsed.frame,
                    source_path=str(path),
                    board=board,
                )
            except (OSError, ValueError) as exc:
                errors += 1
                reason = str(exc).strip()[:200] or type(exc).__name__
                failure_reasons[reason] += 1
                self._store.record_source_file(
                    source_root=root,
                    relative_path=relative_path,
                    market=market,
                    code=code,
                    instrument_type=instrument_type,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=checksum,
                    status="failed",
                    error=reason,
                )
                self._report_progress(progress_callback, index, len(files))
                continue

            if old is None:
                imported_files += 1
                imported_instruments += 1
            else:
                updated_files += 1
                replaced_instruments += 1
            imported_bars += count
            provisional_bars += int((parsed.frame["bar_status"] == "provisional").sum())
            self._store.record_source_file(
                source_root=root,
                relative_path=relative_path,
                market=market,
                code=code,
                instrument_type=instrument_type,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256=checksum,
                status="imported",
                imported=True,
            )
            self._report_progress(progress_callback, index, len(files))

        missing_files = 0
        for relative_path in previous:
            relative_market = relative_path.split("/", 1)[0].lower()
            if (
                relative_market in scanned_markets
                and relative_path not in seen
                and previous[relative_path]["status"] != "missing"
            ):
                self._store.mark_source_missing(root, relative_path)
                missing_files += 1
        self._store.set_meta("last_local_import_at", self._clock().isoformat())
        self._report_progress(progress_callback, len(files), len(files))
        return ImportReport(
            source="local",
            discovered_files=len(files),
            imported_files=imported_files,
            updated_files=updated_files,
            unchanged_files=unchanged_files,
            skipped_files=skipped_files,
            filtered_files=filtered_files,
            missing_files=missing_files,
            imported_instruments=imported_instruments,
            replaced_instruments=replaced_instruments,
            imported_bars=imported_bars,
            provisional_bars=provisional_bars,
            errors=errors,
            failure_reasons=dict(failure_reasons),
        )

    @staticmethod
    def _report_progress(callback: ProgressCallback | None, current: int, total: int) -> None:
        if callback is not None:
            callback(current, total)
