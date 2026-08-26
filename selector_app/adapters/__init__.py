"""Adapters that isolate upstream easy_tdx APIs from application code."""

from .easy_tdx_adapter import EasyTdxAdapter, StockRef, is_supported_a_stock, suggested_vipdoc_path
from .market_sync import EasyTdxMarketSync, MarketSyncConfig, MarketSyncReport

__all__ = [
    "EasyTdxAdapter",
    "EasyTdxMarketSync",
    "MarketSyncConfig",
    "MarketSyncReport",
    "StockRef",
    "is_supported_a_stock",
    "suggested_vipdoc_path",
]
