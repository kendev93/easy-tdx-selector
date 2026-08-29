"""Online market-data synchronization endpoints."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date
from typing import Literal, Protocol, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi import Path as PathParameter
from fastapi.responses import JSONResponse

from selector_app.adapters.easy_tdx_adapter import MarketCode
from selector_app.adapters.market_sync import MarketSyncConfig, MarketSyncReport, ProgressCallback
from selector_app.market_data.service import (
    ChartPeriod,
    LocalInstrumentPage,
    LocalMarketChart,
)
from selector_app.screening.jobs import ScreenJobRunner

from ..schemas import MarketSyncRequest

router = APIRouter(prefix="/market-data", tags=["market-data"])


class MarketSyncService(Protocol):
    def sync(
        self,
        config: MarketSyncConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> MarketSyncReport | dict[str, object]: ...


class LocalMarketDataServiceLike(Protocol):
    def list_instruments(
        self,
        vipdoc_path: str,
        *,
        market: str,
        keyword: str,
        page: int,
        page_size: int,
    ) -> LocalInstrumentPage: ...

    def get_chart(
        self,
        vipdoc_path: str,
        market: MarketCode,
        code: str,
        *,
        period: ChartPeriod,
        start_date: date | None,
        end_date: date | None,
    ) -> LocalMarketChart: ...


def _runner(request: Request) -> ScreenJobRunner:
    return cast(ScreenJobRunner, request.app.state.screen_job_runner)


def _service(request: Request) -> MarketSyncService:
    return cast(MarketSyncService, request.app.state.market_sync_service)


def _local_service(request: Request) -> LocalMarketDataServiceLike:
    return cast(LocalMarketDataServiceLike, request.app.state.local_market_data_service)


def _resolved_vipdoc_path(vipdoc_path: str | None) -> str:
    return vipdoc_path or os.getenv("SELECTOR_VIPDOC_PATH") or "/data/vipdoc"


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def create_sync_job(payload: MarketSyncRequest, request: Request) -> JSONResponse:
    vipdoc_path = _resolved_vipdoc_path(payload.vipdoc_path)
    config = MarketSyncConfig(
        vipdoc_path=vipdoc_path,
        universe=payload.universe,
        bars=payload.bars,
    )
    if not config.root.is_dir():
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "data_directory_error",
                    "message": "容器内 vipdoc 目录不存在，请检查数据卷挂载",
                }
            },
        )

    def run_sync(progress: Callable[[int, int], None]) -> dict[str, object]:
        result = _service(request).sync(config, progress)
        return result.to_dict() if isinstance(result, MarketSyncReport) else result

    try:
        job_id = _runner(request).submit_callable(run_sync, description="行情同步")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="任务执行器暂不可用") from exc
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"data": {"job_id": job_id, "status": "queued"}},
    )


@router.get("/sync/jobs/{job_id}")
def sync_job_status(job_id: str, request: Request) -> dict[str, object]:
    state = _runner(request).get(job_id)
    if state is None or state.description != "行情同步":
        raise HTTPException(status_code=404, detail="行情同步任务不存在或已过期")
    return {"data": state.snapshot()}


@router.get("/local/instruments")
def local_instruments(
    request: Request,
    vipdoc_path: str | None = Query(default=None, min_length=1, max_length=1024),
    market: str = Query(default="all", pattern=r"^(all|SH|SZ)$"),
    keyword: str = Query(default="", max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, object] | JSONResponse:
    try:
        result = _local_service(request).list_instruments(
            _resolved_vipdoc_path(vipdoc_path),
            market=market,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    except (OSError, ValueError) as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "local_data_error", "message": str(exc)}},
        )
    payload = result.to_dict()
    return {
        "data": payload["items"],
        "meta": {
            "total": payload["total"],
            "page": payload["page"],
            "page_size": payload["page_size"],
            "pages": payload["pages"],
        },
    }


@router.get("/local/{market}/{code}/bars")
def local_market_bars(
    request: Request,
    market: Literal["SH", "SZ"],
    code: str = PathParameter(pattern=r"^\d{6}$"),
    vipdoc_path: str | None = Query(default=None, min_length=1, max_length=1024),
    period: ChartPeriod = Query(default="daily"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> dict[str, object] | JSONResponse:
    try:
        result = _local_service(request).get_chart(
            _resolved_vipdoc_path(vipdoc_path),
            market,
            code,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
    except (OSError, ValueError) as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "local_data_error", "message": str(exc)}},
        )
    return {"data": result.to_dict()}
