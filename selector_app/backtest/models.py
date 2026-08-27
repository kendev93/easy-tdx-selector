"""Immutable configuration and serializable result models for formula backtests."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from selector_app.adapters.easy_tdx_adapter import MarketCode, is_supported_a_stock

ExecutionMode = Literal["next_open", "next_close"]
PositionMode = Literal["full", "fixed"]
BacktestValue = float | int | bool | str | None

_CODE_PATTERN = re.compile(r"^\d{6}$")


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for one single-stock daily formula backtest."""

    market: MarketCode
    code: str
    vipdoc_path: str | Path
    buy_signal: str
    sell_signal: str
    formula_text: str | None = None
    formula_parameters: Mapping[str, float] = field(default_factory=dict)
    start_date: date | None = None
    end_date: date | None = None
    initial_cash: float = 100_000.0
    commission: float = 0.0003
    min_commission: float = 5.0
    stamp_tax: float = 0.001
    slippage: float = 0.0
    execution: ExecutionMode = "next_open"
    position_mode: PositionMode = "full"
    fixed_size: int | None = None

    def __post_init__(self) -> None:
        code = self.code.strip()
        buy_signal = self.buy_signal.strip()
        sell_signal = self.sell_signal.strip()
        if self.market not in {"SH", "SZ"} or not _CODE_PATTERN.fullmatch(code):
            raise ValueError("股票市场和代码格式无效")
        if not is_supported_a_stock(self.market, code):
            raise ValueError(f"不支持回测的股票代码: {self.market} {code}")
        if not buy_signal or not sell_signal:
            raise ValueError("买入和卖出信号不能为空")
        if buy_signal == sell_signal:
            raise ValueError("买入信号和卖出信号不能相同")
        if self.execution not in {"next_open", "next_close"}:
            raise ValueError("不支持的成交方式")
        if self.position_mode not in {"full", "fixed"}:
            raise ValueError("不支持的仓位方式")
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("回测开始日期不能晚于结束日期")
        if not math.isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("初始资金必须是大于 0 的有限数字")
        for name, value in {
            "commission": self.commission,
            "min_commission": self.min_commission,
            "stamp_tax": self.stamp_tax,
            "slippage": self.slippage,
        }.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} 必须是大于等于 0 的有限数字")
        if self.position_mode == "fixed":
            if (
                self.fixed_size is None
                or isinstance(self.fixed_size, bool)
                or self.fixed_size < 100
                or self.fixed_size % 100 != 0
            ):
                raise ValueError("固定股数必须是 100 的整数倍且不小于 100")
        elif self.fixed_size is not None:
            raise ValueError("全仓模式不应设置固定股数")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "buy_signal", buy_signal)
        object.__setattr__(self, "sell_signal", sell_signal)
        formula_text = self.formula_text.strip() if self.formula_text else None
        object.__setattr__(self, "formula_text", formula_text or None)
        object.__setattr__(
            self, "formula_parameters", MappingProxyType(dict(self.formula_parameters))
        )


@dataclass(frozen=True)
class BacktestReport:
    """JSON-ready historical backtest output."""

    market: MarketCode
    code: str
    bars: int
    start_date: str
    end_date: str
    buy_signal: str
    sell_signal: str
    performance: Mapping[str, float | None]
    equity_curve: tuple[Mapping[str, BacktestValue], ...]
    trades: tuple[Mapping[str, BacktestValue], ...]
    positions: tuple[Mapping[str, BacktestValue], ...]
    configuration: Mapping[str, BacktestValue]
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "performance", MappingProxyType(dict(self.performance)))
        object.__setattr__(self, "configuration", MappingProxyType(dict(self.configuration)))

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "code": self.code,
            "bars": self.bars,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "buy_signal": self.buy_signal,
            "sell_signal": self.sell_signal,
            "performance": dict(self.performance),
            "equity_curve": [dict(row) for row in self.equity_curve],
            "trades": [dict(row) for row in self.trades],
            "positions": [dict(row) for row in self.positions],
            "configuration": dict(self.configuration),
            "diagnostic": self.diagnostic,
        }
