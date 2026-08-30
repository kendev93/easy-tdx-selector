from __future__ import annotations

import struct
from typing import Any

from .errors import TdxDecodeError


def require_bytes(data: bytes, position: int, size: int, context: str) -> None:
    if position < 0 or position + size > len(data):
        remaining = max(len(data) - position, 0)
        raise TdxDecodeError(
            f"{context}: 数据不足，需要 {size} 字节，偏移 {position}，实际剩余 {remaining} 字节"
        )


def unpack_from(fmt: str, data: bytes, position: int, context: str) -> tuple[Any, ...]:
    size = struct.calcsize(fmt)
    require_bytes(data, position, size, context)
    try:
        return struct.unpack_from(fmt, data, position)
    except struct.error as exc:
        raise TdxDecodeError(f"{context}: 解析失败: {exc}") from exc


def slice_bytes(data: bytes, position: int, size: int, context: str) -> bytes:
    require_bytes(data, position, size, context)
    return data[position : position + size]
