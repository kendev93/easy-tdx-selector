"""Formula selection engine; no web or easy_tdx imports leak into this layer."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd

from selector_app.adapters.easy_tdx_adapter import EasyTdxAdapter, MarketDataAdapter, StockRef
from selector_app.formulas.registry import FORMULA_REGISTRY, FormulaRegistry

from .models import ScanConfig, ScanReport, ScreenMatch

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, "ScanOutcome"], None]


def combine_matches(matches: list[bool], mode: str, minimum_matches: int | None) -> bool:
    if not matches:
        return False
    if mode == "all":
        return all(matches)
    if mode == "any":
        return any(matches)
    if mode == "at_least" and minimum_matches is not None:
        return sum(matches) >= minimum_matches
    return False


@dataclass(frozen=True)
class ScanOutcome:
    result: ScreenMatch | None = None
    skipped_reason: str | None = None
    error_reason: str | None = None


def _date_to_int(value: object) -> int:
    timestamp = pd.Timestamp(value)
    return int(timestamp.strftime("%Y%m%d"))


def _evaluate_frame(
    ref: StockRef,
    frame: pd.DataFrame,
    config: ScanConfig,
    registry: FormulaRegistry,
) -> ScanOutcome:
    if frame.empty:
        return ScanOutcome(skipped_reason="数据为空")

    results = {
        definition.id: definition.calculate(frame.copy(deep=True))
        for definition in registry.formulas_for_signals(config.selected_signals)
    }
    if any(not result.sufficient_data for result in results.values()):
        return ScanOutcome(skipped_reason="数据不足")

    matched_signals = tuple(
        signal_id
        for signal_id in config.selected_signals
        if results[registry.signal(signal_id).formula_id].last_signal_state[
            signal_id.split(".", 1)[1]
        ]
    )
    matched_bools = [signal_id in matched_signals for signal_id in config.selected_signals]
    if not combine_matches(matched_bools, config.combine_mode, config.minimum_matches):
        return ScanOutcome()

    indicator_values: dict[str, float | None] = {}
    for formula_id, result in results.items():
        for name, value in result.last_indicator_values.items():
            indicator_values[f"{formula_id}.{name}"] = value
    last_close = float(frame["close"].iloc[-1])
    return ScanOutcome(
        result=ScreenMatch(
            market=ref.market,
            code=ref.code,
            signal_date=_date_to_int(frame["date"].iloc[-1]),
            last_close=last_close,
            matched_signals=matched_signals,
            match_count=len(matched_signals),
            indicator_values=indicator_values,
        )
    )


def _scan_one_process(ref: StockRef, config: ScanConfig) -> ScanOutcome:
    adapter = EasyTdxAdapter()
    frame = adapter.read_stock(ref)
    return _evaluate_frame(ref, frame, config, FORMULA_REGISTRY)


class ScreenEngine:
    """Scan local daily files and combine selected formula signal states."""

    def __init__(
        self,
        adapter: MarketDataAdapter | None = None,
        registry: FormulaRegistry | None = None,
    ) -> None:
        self._adapter = adapter or EasyTdxAdapter()
        self._registry = registry or FORMULA_REGISTRY

    def scan(
        self,
        config: ScanConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> ScanReport:
        refs = self._adapter.list_stock_refs(
            config.vipdoc_path,
            config.universe,
            config.universe_file,
        )
        if not refs:
            if progress_callback is not None:
                progress_callback(0, 0, ScanOutcome())
            return ScanReport(0, 0, 0, 0, 0, (), {}, {})

        outcomes = self._scan_refs(refs, config, progress_callback)
        results = tuple(outcome.result for outcome in outcomes if outcome.result is not None)
        failures = Counter(
            outcome.error_reason for outcome in outcomes if outcome.error_reason is not None
        )
        skips = Counter(
            outcome.skipped_reason for outcome in outcomes if outcome.skipped_reason is not None
        )
        return ScanReport(
            total_candidates=len(refs),
            total_scanned=len(outcomes),
            total_signals=sum(result.match_count for result in results),
            errors=sum(failures.values()),
            skipped=sum(skips.values()),
            results=results,
            failure_reasons=dict(failures),
            skip_reasons=dict(skips),
        )

    def _scan_refs(
        self,
        refs: list[StockRef],
        config: ScanConfig,
        progress_callback: ProgressCallback | None,
    ) -> list[ScanOutcome]:
        if config.workers <= 1:
            outcomes: list[ScanOutcome] = []
            for current, ref in enumerate(refs, start=1):
                outcome = self._scan_one(ref, config)
                outcomes.append(outcome)
                if progress_callback is not None:
                    progress_callback(current, len(refs), outcome)
            return outcomes

        # The production adapter is process-safe and uses processes for CPU-heavy
        # pandas formulas. Injected adapters (tests/embedding) use threads because
        # arbitrary adapter instances are not guaranteed to be pickleable.
        executor_type = (
            ProcessPoolExecutor if isinstance(self._adapter, EasyTdxAdapter) else ThreadPoolExecutor
        )
        outcomes_by_index: dict[int, ScanOutcome] = {}
        with executor_type(max_workers=config.workers) as executor:
            futures = {
                executor.submit(
                    _scan_one_process if executor_type is ProcessPoolExecutor else self._scan_one,
                    ref,
                    config,
                ): index
                for index, ref in enumerate(refs)
            }
            completed = 0
            for future in as_completed(futures):
                index = futures[future]
                try:
                    outcome = future.result()
                except Exception as exc:  # noqa: BLE001 - per-stock isolation
                    logger.warning(
                        "扫描 %s 失败，继续处理其余股票", refs[index].code, exc_info=True
                    )
                    outcome = ScanOutcome(error_reason=str(exc) or type(exc).__name__)
                outcomes_by_index[index] = outcome
                completed += 1
                if progress_callback is not None:
                    progress_callback(completed, len(refs), outcome)
        return [outcomes_by_index[index] for index in range(len(refs))]

    def _scan_one(self, ref: StockRef, config: ScanConfig) -> ScanOutcome:
        try:
            frame = self._adapter.read_stock(ref)
            return _evaluate_frame(ref, frame, config, self._registry)
        except Exception as exc:  # noqa: BLE001 - one bad stock must not abort scan
            logger.warning("扫描 %s (%s) 失败，已跳过", ref.code, ref.path, exc_info=True)
            return ScanOutcome(error_reason=str(exc) or type(exc).__name__)
