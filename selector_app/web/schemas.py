"""Pydantic request/response schemas for formula-screen APIs."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from selector_app.formulas.custom import FormulaParseError, parse_formula
from selector_app.formulas.registry import FORMULA_REGISTRY
from selector_app.screening.models import ScanConfig


class FormulaScreenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_signals: list[str] = Field(min_length=1, max_length=32)
    combine_mode: Literal["all", "any", "at_least"] = "at_least"
    minimum_matches: int | None = Field(default=None, ge=1, le=32)
    universe: Literal["all", "sh", "sz", "custom"] = "all"
    universe_file: str | None = Field(default=None, max_length=1024)
    vipdoc_path: str = Field(min_length=1, max_length=1024)
    workers: int = Field(default=1, ge=1, le=32)
    period: Literal["daily"] = "daily"
    formula_text: str | None = Field(default=None, max_length=20_000)
    formula_parameters: dict[str, float] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def validate_selection(self) -> FormulaScreenRequest:
        if self.formula_text:
            try:
                parsed = parse_formula(self.formula_text)
            except FormulaParseError as exc:
                raise ValueError(str(exc)) from exc
            available = {signal.id for signal in parsed.signals}
            invalid = [signal for signal in self.selected_signals if signal not in available]
            known_parameters = {parameter.name for parameter in parsed.parameters}
            unknown_parameters = sorted(set(self.formula_parameters) - known_parameters)
            if unknown_parameters:
                raise ValueError(f"未知公式参数: {', '.join(unknown_parameters)}")
            parameters_by_name = {parameter.name: parameter for parameter in parsed.parameters}
            for name, value in self.formula_parameters.items():
                definition = parameters_by_name[name]
                if (
                    not math.isfinite(value)
                    or not definition.minimum <= value <= definition.maximum
                ):
                    raise ValueError(
                        f"参数 {name} 必须在 {definition.minimum:g} 到 {definition.maximum:g} 之间"
                    )
                if definition.step == 1 and not value.is_integer():
                    raise ValueError(f"参数 {name} 必须是整数")
        else:
            invalid = [
                signal
                for signal in self.selected_signals
                if not FORMULA_REGISTRY.has_signal(signal)
            ]
            if self.formula_parameters:
                raise ValueError("预置公式不接受自定义参数")
        if invalid:
            raise ValueError(f"未知选股信号: {', '.join(invalid)}")
        if len(set(self.selected_signals)) != len(self.selected_signals):
            raise ValueError("选股信号不能重复")
        if self.combine_mode == "at_least":
            if self.minimum_matches is None:
                raise ValueError("至少满足 N 个模式必须设置 minimum_matches")
            if self.minimum_matches > len(self.selected_signals):
                raise ValueError("minimum_matches 不能大于已选择信号数量")
        if self.universe == "custom" and not self.universe_file:
            raise ValueError("自定义股票范围必须设置 universe_file")
        return self

    def to_config(self) -> ScanConfig:
        return ScanConfig(
            selected_signals=tuple(self.selected_signals),
            combine_mode=self.combine_mode,
            minimum_matches=self.minimum_matches,
            universe=self.universe,
            universe_file=self.universe_file,
            vipdoc_path=self.vipdoc_path,
            workers=self.workers,
            period=self.period,
            formula_text=self.formula_text,
            formula_parameters=self.formula_parameters,
        )


def validate_vipdoc_path(path: str) -> None:
    resolved = Path(path).expanduser()
    if not resolved.is_dir():
        raise ValueError(f"vipdoc 路径不存在或不是目录: {resolved}")


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str


class CustomFormulaParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula_text: str = Field(min_length=1, max_length=20_000)


class MarketSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    universe: Literal["all", "sh", "sz"] = "all"
    bars: int = Field(default=800, ge=1, le=800)
    vipdoc_path: str | None = Field(default=None, min_length=1, max_length=1024)
