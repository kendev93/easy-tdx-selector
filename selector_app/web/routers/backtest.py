"""Historical formula backtest endpoints."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from selector_app.backtest.models import BacktestConfig, BacktestReport
from selector_app.backtest.service import BacktestProgressCallback, BacktestService
from selector_app.screening.jobs import JobState, ScreenJobRunner, TaskUserError

from ..schemas import BacktestRequest, validate_vipdoc_path

router = APIRouter(prefix="/backtests", tags=["backtests"])


class BacktestServiceLike(Protocol):
    def run(
        self,
        config: BacktestConfig,
        progress_callback: BacktestProgressCallback | None = None,
    ) -> BacktestReport | dict[str, object]: ...


def _runner(request: Request) -> ScreenJobRunner:
    return cast(ScreenJobRunner, request.app.state.screen_job_runner)


def _service(request: Request) -> BacktestServiceLike:
    return cast(BacktestService | BacktestServiceLike, request.app.state.backtest_service)


def _state_or_404(job_id: str, request: Request) -> JobState:
    state = _runner(request).get(job_id)
    if state is None or state.description != "历史回测":
        raise HTTPException(status_code=404, detail="回测任务不存在或已过期")
    return state


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_backtest(payload: BacktestRequest, request: Request) -> JSONResponse:
    try:
        validate_vipdoc_path(payload.vipdoc_path)
        config = payload.to_config()

        def run_backtest(progress: Callable[[int, int], None]) -> dict[str, object]:
            try:
                result = _service(request).run(config, progress)
            except ValueError as exc:
                raise TaskUserError(str(exc)) from exc
            return result.to_dict() if isinstance(result, BacktestReport) else result

        job_id = _runner(request).submit_callable(run_backtest, description="历史回测")
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
def backtest_status(job_id: str, request: Request) -> dict[str, object]:
    state = _state_or_404(job_id, request)
    snapshot = state.snapshot()
    # Keep the polling response small; the dedicated results endpoint owns the
    # potentially large equity/trade payload.
    snapshot["result"] = None
    return {"data": snapshot}


@router.get("/{job_id}/results")
def backtest_results(job_id: str, request: Request) -> dict[str, object]:
    state = _state_or_404(job_id, request)
    if state.status == "failed":
        raise HTTPException(status_code=500, detail=state.error or "回测任务失败")
    if state.status != "completed" or state.result_payload is None:
        raise HTTPException(status_code=409, detail="回测尚未完成")
    return {"data": state.result_payload}
