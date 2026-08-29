"""FastAPI application factory for the standalone selector."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from selector_app.adapters.market_sync import EasyTdxMarketSync
from selector_app.backtest.service import BacktestService
from selector_app.market_data.service import LocalMarketDataService
from selector_app.portfolio_backtest.service import PortfolioBacktestService
from selector_app.screening.jobs import ScanEngineLike, ScreenJobRunner
from selector_app.strategy_fitness.service import StrategyFitnessService

from .routers.formula_screen import router as formula_screen_router

logger = logging.getLogger(__name__)


def create_app(
    *,
    engine: ScanEngineLike | None = None,
    runner: ScreenJobRunner | None = None,
    market_sync: EasyTdxMarketSync | object | None = None,
    backtest_service: BacktestService | object | None = None,
    portfolio_backtest_service: PortfolioBacktestService | object | None = None,
    strategy_fitness_service: StrategyFitnessService | object | None = None,
    local_market_data_service: LocalMarketDataService | object | None = None,
) -> FastAPI:
    owns_runner = runner is None
    selected_runner = runner or ScreenJobRunner(engine=engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_runner:
            selected_runner.shutdown()

    app = FastAPI(
        title="Easy TDX 选股台",
        description="基于 easy-tdx 本地日线数据的公式选股 API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.screen_job_runner = selected_runner
    app.state.market_sync_service = market_sync or EasyTdxMarketSync()
    app.state.backtest_service = backtest_service or BacktestService()
    app.state.portfolio_backtest_service = portfolio_backtest_service or PortfolioBacktestService()
    app.state.strategy_fitness_service = strategy_fitness_service or StrategyFitnessService()
    app.state.local_market_data_service = local_market_data_service or LocalMarketDataService()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        messages = [error.get("msg", "请求参数无效") for error in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "；".join(messages),
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code_by_status = {
            404: "not_found",
            409: "conflict",
            422: "validation_error",
            503: "service_unavailable",
        }
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code_by_status.get(exc.status_code, "request_error"),
                    "message": message,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理的 API 异常", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "服务器内部错误，请稍后重试"}},
        )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    from .routers.backtest import router as backtest_router
    from .routers.market_data import router as market_data_router
    from .routers.portfolio_backtest import router as portfolio_backtest_router
    from .routers.strategy_fitness import router as strategy_fitness_router

    app.include_router(formula_screen_router, prefix="/api/v1")
    app.include_router(market_data_router, prefix="/api/v1")
    app.include_router(backtest_router, prefix="/api/v1")
    app.include_router(portfolio_backtest_router, prefix="/api/v1")
    app.include_router(strategy_fitness_router, prefix="/api/v1")
    return app


app = create_app()
