"""Backward-compatible import shim for the project-owned local adapter.

The historical module path is kept for embedders, but it contains no import of
the external ``easy-tdx`` package.
"""

from selector_app.market_data.adapter import MarketDataAdapter
from selector_app.market_data.local_adapter import (
    LocalDayMarketDataAdapter,
    MarketCode,
    StockRef,
    is_supported_a_stock,
    is_supported_instrument,
    suggested_vipdoc_path,
)

EasyTdxAdapter = LocalDayMarketDataAdapter

__all__ = [
    "EasyTdxAdapter",
    "LocalDayMarketDataAdapter",
    "MarketCode",
    "MarketDataAdapter",
    "StockRef",
    "is_supported_a_stock",
    "is_supported_instrument",
    "suggested_vipdoc_path",
]
