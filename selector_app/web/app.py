"""FastAPI application factory for the standalone selector."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from selector_app.screening.jobs import ScanEngineLike, ScreenJobRunner

from .routers.formula_screen import router as formula_screen_router

logger = logging.getLogger(__name__)


def create_app(
    *,
    engine: ScanEngineLike | None = None,
    runner: ScreenJobRunner | None = None,
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

    app.include_router(formula_screen_router, prefix="/api/v1")
    return app


app = create_app()
