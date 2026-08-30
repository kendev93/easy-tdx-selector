"""Immutable screening domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from selector_app.market_data.models import InstrumentBoard, InstrumentType
from selector_app.market_data.scope import InstrumentScope

CombineMode = Literal["all", "any", "at_least"]
Universe = Literal["all", "sh", "sz", "custom"]


@dataclass(frozen=True)
class ScanConfig:
    selected_signals: tuple[str, ...]
    combine_mode: CombineMode | str
    minimum_matches: int | None
    universe: Universe | str
    universe_file: str | None
    vipdoc_path: str
    workers: int
    period: str
    instrument_types: tuple[InstrumentType, ...] = ()
    boards: tuple[InstrumentBoard, ...] = ()
    formula_text: str | None = None
    formula_parameters: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        scope = InstrumentScope.from_values(
            universe=str(self.universe),
            instrument_types=self.instrument_types,
            boards=self.boards,
        )
        object.__setattr__(self, "instrument_types", scope.instrument_types or ())
        object.__setattr__(self, "boards", scope.boards or ())
        object.__setattr__(
            self, "formula_parameters", MappingProxyType(dict(self.formula_parameters))
        )


@dataclass(frozen=True)
class ScreenMatch:
    market: str
    code: str
    signal_date: int
    last_close: float
    matched_signals: tuple[str, ...]
    match_count: int
    indicator_values: Mapping[str, float | None]
    instrument_type: str = "stock"
    board: InstrumentBoard = "main"
    name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "indicator_values", MappingProxyType(dict(self.indicator_values)))

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "code": self.code,
            "name": self.name,
            "signal_date": self.signal_date,
            "last_close": self.last_close,
            "matched_signals": list(self.matched_signals),
            "match_count": self.match_count,
            "indicator_values": dict(self.indicator_values),
            "instrument_type": self.instrument_type,
            "board": self.board,
        }


@dataclass(frozen=True)
class ScanReport:
    total_candidates: int
    total_scanned: int
    total_signals: int
    errors: int
    skipped: int
    results: tuple[ScreenMatch, ...]
    failure_reasons: Mapping[str, int]
    skip_reasons: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "failure_reasons", MappingProxyType(dict(self.failure_reasons)))
        object.__setattr__(self, "skip_reasons", MappingProxyType(dict(self.skip_reasons)))

    def summary_dict(self) -> dict[str, object]:
        return {
            "total_candidates": self.total_candidates,
            "total_scanned": self.total_scanned,
            "total_signals": self.total_signals,
            "errors": self.errors,
            "skipped": self.skipped,
            "failure_reasons": dict(self.failure_reasons),
            "skip_reasons": dict(self.skip_reasons),
        }
