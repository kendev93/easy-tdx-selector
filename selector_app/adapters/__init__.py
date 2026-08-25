"""Adapters that isolate upstream easy_tdx APIs from application code."""

from .easy_tdx_adapter import EasyTdxAdapter, StockRef, suggested_vipdoc_path

__all__ = ["EasyTdxAdapter", "StockRef", "suggested_vipdoc_path"]
