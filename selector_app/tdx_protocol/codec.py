from __future__ import annotations

import struct
import zlib

from .binary import slice_bytes, unpack_from
from .errors import TdxDecodeError
from .types import Market, SecurityInfo

HEADER_SIZE = 16
_HEADER_FORMAT = "<IIIHH"


def decode_frame_header(data: bytes) -> tuple[int, int, int, int, int]:
    return unpack_from(_HEADER_FORMAT, data, 0, "响应帧头")


def decompress_body(data: bytes, header: tuple[int, int, int, int, int]) -> bytes:
    _magic, _sequence, _method, compressed_size, uncompressed_size = header
    if len(data) != compressed_size:
        raise TdxDecodeError(f"响应帧长度不符: header={compressed_size}, actual={len(data)}")
    if compressed_size == uncompressed_size:
        body = data
    else:
        try:
            body = zlib.decompress(data)
        except zlib.error as exc:
            raise TdxDecodeError(f"响应帧解压失败: {exc}") from exc
    if len(body) != uncompressed_size:
        raise TdxDecodeError(f"响应帧解压长度不符: header={uncompressed_size}, actual={len(body)}")
    return body


def decode_price(data: bytes, position: int) -> tuple[int, int]:
    start = position
    try:
        first = data[position]
        value = first & 0x3F
        negative = bool(first & 0x40)
        shift = 6
        position += 1
        while first & 0x80:
            first = data[position]
            value |= (first & 0x7F) << shift
            shift += 7
            position += 1
    except IndexError as exc:
        raise TdxDecodeError(f"价格变长整数截断: offset={start}") from exc
    return (-value if negative else value), position


def decode_volume(data: bytes, position: int) -> tuple[float, int]:
    (raw,) = unpack_from("<I", data, position, "成交量")
    return _decode_volume(raw), position + 4


def _decode_volume(value: int) -> float:
    if value == 0:
        return 0.0
    logpoint = (value >> 24) & 0xFF
    high = (value >> 16) & 0xFF
    middle = (value >> 8) & 0xFF
    low = value & 0xFF

    base = _pow2(logpoint * 2 - 0x7F)
    high_exp = logpoint * 2 - 0x86
    if high > 0x80:
        high_value = _pow2(high_exp) * 128 + (high & 0x7F) * _pow2(high_exp + 1)
    else:
        high_value = _pow2(high_exp) * high
    middle_value = _pow2(logpoint * 2 - 0x8E) * middle
    low_value = _pow2(logpoint * 2 - 0x96) * low
    if high & 0x80:
        middle_value *= 2.0
        low_value *= 2.0
    return base + high_value + middle_value + low_value


def _pow2(exponent: int) -> float:
    if exponent >= 0:
        return float(1 << exponent) if exponent < 63 else 2.0**exponent
    return 1.0 / (1 << (-exponent)) if -exponent < 63 else 2.0**exponent


def decode_day(data: bytes, position: int) -> tuple[int, int, int, int]:
    (value,) = unpack_from("<I", data, position, "日线日期")
    return value // 10000, (value % 10000) // 100, value % 100, position + 4


def decode_security_bar(data: bytes, position: int) -> tuple[object, int]:
    from .types import SecurityBar

    start = position
    year, month, day, position = decode_day(data, position)
    opening, position = decode_price(data, position)
    closing, position = decode_price(data, position)
    high, position = decode_price(data, position)
    low, position = decode_price(data, position)
    volume, position = decode_volume(data, position)
    amount, position = decode_volume(data, position)
    opening_abs = opening
    closing_abs = opening_abs + closing
    high_abs = opening_abs + high
    low_abs = opening_abs + low
    return (
        SecurityBar(
            open=opening_abs / 1000.0,
            close=closing_abs / 1000.0,
            high=high_abs / 1000.0,
            low=low_abs / 1000.0,
            volume=volume,
            amount=amount,
            year=year,
            month=month,
            day=day,
            raw=data[start:position],
        ),
        position,
    )


def decode_security_list(data: bytes, market: Market) -> list[SecurityInfo]:
    (count,) = unpack_from("<H", data, 0, "证券列表数量")
    position = 2
    result: list[SecurityInfo] = []
    for _ in range(count):
        raw = slice_bytes(data, position, 29, "证券列表记录")
        code_bytes, volume_unit, name_bytes, _unknown, decimal_point, pre_close_raw, _unknown2 = (
            struct.unpack("<6sH8s4sBI4s", raw)
        )
        code = code_bytes.decode("ascii", errors="replace").rstrip("\x00")
        name = name_bytes.decode("gbk", errors="replace").rstrip("\x00")
        result.append(
            SecurityInfo(
                market=market,
                code=code,
                name=name,
                volume_unit=volume_unit,
                decimal_point=decimal_point,
                pre_close=_decode_volume(pre_close_raw),
            )
        )
        position += 29
    return result
