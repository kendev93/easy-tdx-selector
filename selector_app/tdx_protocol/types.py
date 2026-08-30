from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Market(IntEnum):
    SZ = 0
    SH = 1


class KlineCategory(IntEnum):
    DAY = 4


@dataclass(frozen=True)
class SecurityBar:
    open: float
    close: float
    high: float
    low: float
    volume: float
    amount: float
    year: int
    month: int
    day: int
    hour: int = 15
    minute: int = 0
    raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass(frozen=True)
class SecurityInfo:
    market: Market
    code: str
    name: str = ""
    volume_unit: int = 100
    decimal_point: int = 2
    pre_close: float = 0.0
