"""Online market-data synchronization endpoints."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date
from typing import Literal, Protocol, cast

import duckdb
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi import Path as PathParameter
from fastapi.responses import JSONResponse

from selector_app.adapters.market_sync import MarketSyncConfig, MarketSyncReport, ProgressCallback
from selector_app.market_data.day_importer import ProgressCallback as LocalImportProgressCallback
from selector_app.market_data.models import (
    ImportReport,
    InstrumentBoard,
    InstrumentType,
    MarketCode,
)
from selector_app.market_data.service import (
    ChartPeriod,
    LocalInstrumentPage,
    LocalMarketChart,
)
from selector_app.market_data.store import DuckDbMarketDataStore, MarketDataStoreError
from selector_app.screening.jobs import ScreenJobRunner, TaskUserError

from ..schemas import LocalMarketImportRequest, MarketSyncRequest

router = APIRouter(prefix="/market-data", tags=["market-data"])


class MarketSyncService(Protocol):
    def sync(
        self,
        config: MarketSyncConfig,
        progress_callback: LocalImportProgressCallback | None = None,
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


class LocalDayImporterLike(Protocol):
    def import_vipdoc(
        self,
        vipdoc_path: str,
        *,
        universe: str = "all",
        instrument_types: list[InstrumentType] | None = None,
        boards: list[InstrumentBoard] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ImportReport | dict[str, object]: ...


def _runner(request: Request) -> ScreenJobRunner:
    return cast(ScreenJobRunner, request.app.state.screen_job_runner)


def _service(request: Request) -> MarketSyncService:
    return cast(MarketSyncService, request.app.state.market_sync_service)


def _local_service(request: Request) -> LocalMarketDataServiceLike:
    return cast(LocalMarketDataServiceLike, request.app.state.local_market_data_service)


def _store(request: Request) -> DuckDbMarketDataStore:
    return cast(DuckDbMarketDataStore, request.app.state.market_data_store)


def _importer(request: Request) -> LocalDayImporterLike:
    return cast(LocalDayImporterLike, request.app.state.local_day_importer)


def _resolved_vipdoc_path(vipdoc_path: str | None) -> str:
    return vipdoc_path or os.getenv("SELECTOR_VIPDOC_PATH") or "/data/vipdoc"


@router.post("/import-local", status_code=status.HTTP_202_ACCEPTED)
def create_local_import(
    payload: LocalMarketImportRequest,
    request: Request,
) -> JSONResponse:
    root = os.path.abspath(os.path.expanduser(payload.vipdoc_path))
    if not os.path.isdir(root):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "data_directory_error",
                    "message": f"vipdoc 目录不存在或不是目录: {root}",
                }
            },
        )

    def run_import(progress: Callable[[int, int], None]) -> dict[str, object]:
        try:
            result = _importer(request).import_vipdoc(
                root,
                universe=payload.universe,
                instrument_types=payload.instrument_types,
                boards=payload.boards,
                progress_callback=progress,
            )
        except (MarketDataStoreError, duckdb.Error) as exc:
            raise TaskUserError(_storage_error_message(exc)) from exc
        return result.to_dict() if isinstance(result, ImportReport) else result

    try:
        job_id = _runner(request).submit_callable(run_import, description="本地行情导入")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="任务执行器暂不可用") from exc
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"data": {"job_id": job_id, "status": "queued"}},
    )


@router.get("/jobs/{job_id}")
def market_data_job_status(job_id: str, request: Request) -> dict[str, object]:
    state = _runner(request).get(job_id)
    if state is None or state.description not in {"本地行情导入", "行情同步"}:
        raise HTTPException(status_code=404, detail="行情任务不存在或已过期")
    return {"data": state.snapshot()}


@router.get("/store", response_model=None)
def market_data_store_status(request: Request) -> dict[str, object] | JSONResponse:
    try:
        return {"data": _store(request).status().to_dict()}
    except (MarketDataStoreError, duckdb.Error, OSError) as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "market_data_store_error",
                    "message": _storage_error_message(exc),
                }
            },
        )


@router.post("/sync-online", status_code=status.HTTP_202_ACCEPTED)
@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def create_sync_job(payload: MarketSyncRequest, request: Request) -> JSONResponse:
    config = MarketSyncConfig(
        universe=payload.universe,
        bars=payload.bars,
        instrument_types=tuple(payload.instrument_types or ()),
        boards=tuple(payload.boards or ()),
    )

    def run_sync(progress: Callable[[int, int], None]) -> dict[str, object]:
        try:
            result = _service(request).sync(config, progress)
        except (MarketDataStoreError, duckdb.Error) as exc:
            raise TaskUserError(_storage_error_message(exc)) from exc
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


@router.get("/local/instruments", response_model=None)
def local_instruments(
    request: Request,
    market: str = Query(default="all", pattern=r"^(all|SH|SZ)$"),
    keyword: str = Query(default="", max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, object] | JSONResponse:
    try:
        result = _local_service(request).list_instruments(
            _resolved_vipdoc_path(None),
            market=market,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    except (OSError, ValueError, MarketDataStoreError, duckdb.Error) as exc:
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


@router.get("/local/{market}/{code}/bars", response_model=None)
def local_market_bars(
    request: Request,
    market: Literal["SH", "SZ"],
    code: str = PathParameter(pattern=r"^\d{6}$"),
    period: ChartPeriod = Query(default="daily"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> dict[str, object] | JSONResponse:
    try:
        result = _local_service(request).get_chart(
            _resolved_vipdoc_path(None),
            market,
            code,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
    except (OSError, ValueError, MarketDataStoreError, duckdb.Error) as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "local_data_error", "message": str(exc)}},
        )
    return {"data": result.to_dict()}


def _storage_error_message(exc: BaseException) -> str:
    if isinstance(exc, MarketDataStoreError):
        return str(exc)
    message = str(exc).lower()
    if "lock" in message or "conflicting" in message:
        return "行情数据库当前被其它进程占用，请关闭其它写入进程后重试"
    return "行情数据库无法读取，请检查文件权限或数据库完整性"
