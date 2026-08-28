"""Run parsed formula signals through easy_tdx's historical trade engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Protocol, cast

import numpy as np
import pandas as pd
from easy_tdx.backtest import BacktestEngine, BacktestResult, Strategy

from selector_app.adapters.easy_tdx_adapter import EasyTdxAdapter, MarketCode, StockRef
from selector_app.formulas.common import validate_market_data
from selector_app.formulas.custom import ParsedFormula, evaluate_custom_formula, parse_formula
from selector_app.formulas.registry import FORMULA_REGISTRY, FormulaRegistry
from selector_app.formulas.types import FormulaResult

from .models import BacktestConfig, BacktestReport, BacktestValue

BacktestProgressCallback = Callable[[int, int], None]


class BacktestMarketDataAdapter(Protocol):
    def stock_ref(self, vipdoc_path: str | Path, market: MarketCode, code: str) -> StockRef: ...

    def read_stock(self, ref: StockRef) -> pd.DataFrame: ...


class BacktestService:
    """Calculate causal formula signals and simulate their trades."""

    def __init__(
        self,
        adapter: BacktestMarketDataAdapter | None = None,
        registry: FormulaRegistry | None = None,
    ) -> None:
        self._adapter = adapter or EasyTdxAdapter()
        self._registry = registry or FORMULA_REGISTRY

    def run(
        self,
        config: BacktestConfig,
        progress_callback: BacktestProgressCallback | None = None,
    ) -> BacktestReport:
        if progress_callback is not None:
            progress_callback(0, 1)
        ref = self._adapter.stock_ref(config.vipdoc_path, config.market, config.code)
        frame = self._prepare_frame(self._adapter.read_stock(ref))
        if frame.empty:
            raise ValueError(f"{config.market} {config.code} 没有可用日线数据")

        parsed_formula, formula_results = self._calculate_formula_results(frame, config)
        minimum_bars = max(result.minimum_bars for result in formula_results.values())
        if len(frame) < minimum_bars:
            raise ValueError(
                f"历史数据不足，至少需要 {minimum_bars} 根 K 线，当前只有 {len(frame)} 根"
            )

        window_indices = self._window_indices(frame, config.start_date, config.end_date)
        if len(window_indices) == 0:
            raise ValueError("指定日期范围内没有可用日线数据")
        window = frame.iloc[window_indices].reset_index(drop=True)
        buy_mask = self._signal_window(
            formula_results,
            config.buy_signal,
            window_indices,
            parsed_formula is not None,
        )
        sell_mask = self._signal_window(
            formula_results,
            config.sell_signal,
            window_indices,
            parsed_formula is not None,
        )
        result = self._run_engine(window, buy_mask, sell_mask, config)
        report = self._build_report(result, window, config)
        if progress_callback is not None:
            progress_callback(1, 1)
        return report

    def _calculate_formula_results(
        self,
        frame: pd.DataFrame,
        config: BacktestConfig,
    ) -> tuple[ParsedFormula | None, dict[str, FormulaResult]]:
        if config.formula_text:
            parsed = parse_formula(config.formula_text)
            available = {signal.id for signal in parsed.signals}
            if config.buy_signal not in available or config.sell_signal not in available:
                raise ValueError("买入或卖出信号不属于当前自定义公式")
            return parsed, {
                "custom": evaluate_custom_formula(parsed, frame, config.formula_parameters)
            }

        for signal_id in (config.buy_signal, config.sell_signal):
            if not self._registry.has_signal(signal_id):
                raise ValueError(f"未知选股信号: {signal_id}")
        results = {
            definition.id: definition.calculate(frame.copy(deep=True))
            for definition in self._registry.formulas_for_signals(
                (config.buy_signal, config.sell_signal)
            )
        }
        return None, results

    @staticmethod
    def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
        prepared = frame.copy(deep=True)
        validate_market_data(prepared)
        prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
        if prepared["date"].isna().any():
            raise ValueError("行情数据包含无效日期")
        return prepared.sort_values("date", kind="stable").reset_index(drop=True)

    @staticmethod
    def _window_indices(
        frame: pd.DataFrame,
        start_date: date | None,
        end_date: date | None,
    ) -> np.ndarray:
        dates = frame["date"].dt.date
        mask = pd.Series(True, index=frame.index)
        if start_date is not None:
            mask &= dates >= start_date
        if end_date is not None:
            mask &= dates <= end_date
        return np.flatnonzero(mask.to_numpy())

    def _signal_window(
        self,
        results: Mapping[str, FormulaResult],
        signal_id: str,
        indices: np.ndarray,
        custom: bool,
    ) -> np.ndarray:
        if custom:
            result = results["custom"]
            key = signal_id
        else:
            definition = self._registry.signal(signal_id)
            result = results[definition.formula_id]
            key = signal_id.split(".", 1)[1]
        try:
            values = result.signals[key]
        except KeyError as exc:
            raise ValueError(f"找不到信号输出: {signal_id}") from exc
        signal_array = np.array(cast(object, values), dtype=bool, copy=True)
        return cast(np.ndarray, signal_array[indices].copy())

    @staticmethod
    def _run_engine(
        frame: pd.DataFrame,
        buy_mask: np.ndarray,
        sell_mask: np.ndarray,
        config: BacktestConfig,
    ) -> BacktestResult:
        data = frame.rename(columns={"date": "datetime", "volume": "vol"})[
            ["datetime", "open", "high", "low", "close", "vol", "amount"]
        ]
        order_size = 0 if config.position_mode == "full" else cast(int, config.fixed_size)

        class FormulaSignalStrategy(Strategy):  # type: ignore[misc, unused-ignore]
            def __init__(self) -> None:
                super().__init__()
                self._cursor = -1

            def init(self) -> None:
                self._cursor = -1

            def next(self) -> None:
                self._cursor += 1
                if self.position["size"] > 0:
                    if bool(sell_mask[self._cursor]):
                        self.sell(size=order_size)
                elif bool(buy_mask[self._cursor]):
                    self.buy(size=order_size)

        return BacktestEngine(
            FormulaSignalStrategy,
            cash=config.initial_cash,
            commission=config.commission,
            min_commission=config.min_commission,
            stamp_tax=config.stamp_tax,
            slippage=config.slippage,
            execution=config.execution,
            position_mode=config.position_mode,
            reject_policy="reduce",
        ).run(data)

    @staticmethod
    def _build_report(
        result: BacktestResult,
        frame: pd.DataFrame,
        config: BacktestConfig,
    ) -> BacktestReport:
        # The result shape is the stable public easy_tdx.backtest.BacktestResult
        # contract; keeping serialization here prevents pandas/numpy values from
        # leaking into JSONResponse.
        dates = frame["date"]
        return BacktestReport(
            market=config.market,
            code=config.code,
            bars=len(frame),
            start_date=dates.iloc[0].strftime("%Y-%m-%d"),
            end_date=dates.iloc[-1].strftime("%Y-%m-%d"),
            buy_signal=config.buy_signal,
            sell_signal=config.sell_signal,
            performance={name: _number(value) for name, value in result.performance.items()},
            equity_curve=tuple(_frame_records(result.equity_curve)),
            trades=tuple(_frame_records(result.trades)),
            positions=tuple(_frame_records(result.positions)),
            configuration={
                "initial_cash": config.initial_cash,
                "commission": config.commission,
                "min_commission": config.min_commission,
                "stamp_tax": config.stamp_tax,
                "slippage": config.slippage,
                "execution": config.execution,
                "position_mode": config.position_mode,
                "fixed_size": config.fixed_size,
            },
            diagnostic=result.diagnostic,
        )


def _number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(cast(float, value))


def _date_value(value: object) -> str:
    if isinstance(value, (int, np.integer)):
        timestamp = pd.to_datetime(str(int(value)), format="%Y%m%d")
        return str(timestamp.strftime("%Y-%m-%d"))
    return str(pd.Timestamp(value).strftime("%Y-%m-%d"))


def _json_value(value: object) -> BacktestValue:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    return str(value)


def _frame_records(frame: pd.DataFrame) -> list[dict[str, BacktestValue]]:
    records: list[dict[str, BacktestValue]] = []
    for source in frame.to_dict(orient="records"):
        record: dict[str, BacktestValue] = {}
        for name, value in source.items():
            if name == "datetime":
                record["date"] = _date_value(value)
            else:
                record[name] = _json_value(value)
        records.append(record)
    return records
