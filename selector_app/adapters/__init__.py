"""Compatibility exports for application-owned market-data adapters."""

from selector_app.market_data.local_adapter import (
    LocalDayMarketDataAdapter,
    StockRef,
    is_supported_a_stock,
    suggested_vipdoc_path,
)

from .market_sync import EasyTdxMarketSync, MarketSyncConfig, MarketSyncReport, TdxMarketSync

EasyTdxAdapter = LocalDayMarketDataAdapter

__all__ = [
    "EasyTdxAdapter",
    "EasyTdxMarketSync",
    "MarketSyncConfig",
    "MarketSyncReport",
    "StockRef",
    "LocalDayMarketDataAdapter",
    "is_supported_a_stock",
    "suggested_vipdoc_path",
    "TdxMarketSync",
]
