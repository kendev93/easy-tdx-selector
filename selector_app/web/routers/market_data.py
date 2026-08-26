"""Online market-data synchronization endpoints."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from selector_app.adapters.market_sync import MarketSyncConfig, MarketSyncReport, ProgressCallback
from selector_app.screening.jobs import ScreenJobRunner

from ..schemas import MarketSyncRequest

router = APIRouter(prefix="/market-data", tags=["market-data"])


class MarketSyncService(Protocol):
    def sync(
        self,
        config: MarketSyncConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> MarketSyncReport | dict[str, object]: ...


def _runner(request: Request) -> ScreenJobRunner:
    return cast(ScreenJobRunner, request.app.state.screen_job_runner)


def _service(request: Request) -> MarketSyncService:
    return cast(MarketSyncService, request.app.state.market_sync_service)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def create_sync_job(payload: MarketSyncRequest, request: Request) -> JSONResponse:
    vipdoc_path = payload.vipdoc_path or os.getenv("SELECTOR_VIPDOC_PATH") or "/data/vipdoc"
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
