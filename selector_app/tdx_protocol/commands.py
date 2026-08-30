from __future__ import annotations

import logging
import struct
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from .binary import slice_bytes, unpack_from
from .codec import decode_day, decode_price, decode_security_list, decode_volume
from .errors import TdxDecodeError
from .types import KlineCategory, Market, SecurityBar, SecurityInfo

T = TypeVar("T")
_LOGGER = logging.getLogger(__name__)


class Command(ABC, Generic[T]):
    @abstractmethod
    def build_request(self) -> bytes: ...

    @abstractmethod
    def parse_response(self, body: bytes) -> T: ...


class GetSecurityCount(Command[int]):
    def __init__(self, market: Market) -> None:
        self.market = market

    def build_request(self) -> bytes:
        return (
            bytes.fromhex("0c0c186c0001080008004e04")
            + struct.pack("<H", int(self.market))
            + bytes.fromhex("75c73301")
        )

    def parse_response(self, body: bytes) -> int:
        (count,) = unpack_from("<H", body, 0, "证券数量")
        return int(count)


class GetSecurityList(Command[list[SecurityInfo]]):
    def __init__(self, market: Market, start: int) -> None:
        if start < 0:
            raise ValueError("证券列表起始位置不能为负数")
        self.market = market
        self.start = start

    def build_request(self) -> bytes:
        return bytes.fromhex("0c0118640101060006005004") + struct.pack(
            "<HHH", int(self.market), self.start, 0
        )

    def parse_response(self, body: bytes) -> list[SecurityInfo]:
        return decode_security_list(body, self.market)


class GetSecurityBars(Command[list[SecurityBar]]):
    def __init__(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int,
        *,
        is_index: bool = False,
    ) -> None:
        if start < 0 or not 1 <= count <= 800:
            raise ValueError("TDX 日线分页参数无效")
        if len(code) != 6 or not code.isdigit():
            raise ValueError("TDX 证券代码必须是六位数字")
        self.market = market
        self.code = code
        self.category = category
        self.start = start
        self.count = count
        self.is_index = is_index

    def build_request(self) -> bytes:
        return struct.pack(
            "<HIHHHH6sHHHHIIH",
            0x010C,
            0x01016408,
            0x001C,
            0x001C,
            0x052D,
            int(self.market),
            self.code.encode("ascii"),
            int(self.category),
            1,
            self.start,
            self.count,
            0,
            0,
            0,
        )

    def parse_response(self, body: bytes) -> list[SecurityBar]:
        if len(body) < 2:
            _LOGGER.warning("K线响应为空或缺少数量头，返回空列表")
            return []
        (count,) = unpack_from("<H", body, 0, "K线数量")
        position = 2
        result: list[SecurityBar] = []
        previous_close_base = 0
        for index in range(count):
            try:
                year, month, day, position = decode_day(body, position)
                open_diff, position = decode_price(body, position)
                close_diff, position = decode_price(body, position)
                high_diff, position = decode_price(body, position)
                low_diff, position = decode_price(body, position)
                volume, position = decode_volume(body, position)
                amount, position = decode_volume(body, position)
                if self.is_index:
                    slice_bytes(body, position, 4, "指数K线涨跌家数")
                    position += 4
            except TdxDecodeError as exc:
                _LOGGER.warning(
                    "K线响应在第 %d/%d 条处截断，返回前 %d 条: %s",
                    index + 1,
                    count,
                    len(result),
                    exc,
                )
                return result
            opening = open_diff + previous_close_base
            close = opening + close_diff
            high = opening + high_diff
            low = opening + low_diff
            previous_close_base = close
            result.append(
                SecurityBar(
                    open=opening / 1000.0,
                    close=close / 1000.0,
                    high=high / 1000.0,
                    low=low / 1000.0,
                    volume=volume,
                    amount=amount,
                    year=year,
                    month=month,
                    day=day,
                )
            )
        return result
