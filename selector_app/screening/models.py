"""Immutable screening domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

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


@dataclass(frozen=True)
class ScreenMatch:
    market: str
    code: str
    signal_date: int
    last_close: float
    matched_signals: tuple[str, ...]
    match_count: int
    indicator_values: Mapping[str, float | None]

    def __post_init__(self) -> None:
        object.__setattr__(self, "indicator_values", MappingProxyType(dict(self.indicator_values)))

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "code": self.code,
            "signal_date": self.signal_date,
            "last_close": self.last_close,
            "matched_signals": list(self.matched_signals),
            "match_count": self.match_count,
            "indicator_values": dict(self.indicator_values),
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
