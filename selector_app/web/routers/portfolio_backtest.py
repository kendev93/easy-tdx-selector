"""Dynamic ranked-slot portfolio backtest endpoints."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from selector_app.portfolio_backtest.models import (
    PortfolioBacktestConfig,
    PortfolioBacktestReport,
)
from selector_app.portfolio_backtest.service import (
    PortfolioBacktestProgressCallback,
    PortfolioBacktestService,
)
from selector_app.screening.jobs import JobState, ScreenJobRunner, TaskUserError

from ..schemas import PortfolioBacktestRequest, validate_vipdoc_path

router = APIRouter(prefix="/portfolio-backtests", tags=["portfolio-backtests"])


class PortfolioBacktestServiceLike(Protocol):
    def run(
        self,
        config: PortfolioBacktestConfig,
        progress_callback: PortfolioBacktestProgressCallback | None = None,
    ) -> PortfolioBacktestReport | dict[str, object]: ...


def _runner(request: Request) -> ScreenJobRunner:
    return cast(ScreenJobRunner, request.app.state.screen_job_runner)


def _service(request: Request) -> PortfolioBacktestServiceLike:
    return cast(
        PortfolioBacktestService | PortfolioBacktestServiceLike,
        request.app.state.portfolio_backtest_service,
    )


def _state_or_404(job_id: str, request: Request) -> JobState:
    state = _runner(request).get(job_id)
    if state is None or state.description != "组合回测":
        raise HTTPException(status_code=404, detail="组合回测任务不存在或已过期")
    return state


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_portfolio_backtest(
    payload: PortfolioBacktestRequest,
    request: Request,
) -> JSONResponse:
    try:
        validate_vipdoc_path(payload.vipdoc_path)
        if payload.universe == "custom" and payload.universe_file:
            if not Path(payload.universe_file).expanduser().is_file():
                raise ValueError(f"自定义股票列表文件不存在: {payload.universe_file}")
        config = payload.to_config()

        def run_backtest(progress: Callable[[int, int], None]) -> dict[str, object]:
            try:
                result = _service(request).run(config, progress)
            except ValueError as exc:
                raise TaskUserError(str(exc)) from exc
            return result.to_dict() if isinstance(result, PortfolioBacktestReport) else result

        job_id = _runner(request).submit_callable(run_backtest, description="组合回测")
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "validation_error", "message": str(exc)}},
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="任务执行器暂不可用") from exc
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"data": {"job_id": job_id, "status": "queued"}},
    )


@router.get("/{job_id}")
def portfolio_backtest_status(job_id: str, request: Request) -> dict[str, object]:
    state = _state_or_404(job_id, request)
    snapshot = state.snapshot()
    snapshot["result"] = None
    return {"data": snapshot}


@router.get("/{job_id}/results")
def portfolio_backtest_results(job_id: str, request: Request) -> dict[str, object]:
    state = _state_or_404(job_id, request)
    if state.status == "failed":
        raise HTTPException(status_code=500, detail=state.error or "组合回测任务失败")
    if state.status != "completed" or state.result_payload is None:
        raise HTTPException(status_code=409, detail="组合回测尚未完成")
    return {"data": state.result_payload}
