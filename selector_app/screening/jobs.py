"""Small in-process job runner for long-running local scans."""

from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal, Protocol

from .engine import ProgressCallback, ScanOutcome, ScreenEngine
from .models import ScanConfig, ScanReport

logger = logging.getLogger(__name__)
JobStatus = Literal["queued", "running", "completed", "failed"]


class ScanEngineLike(Protocol):
    def scan(
        self,
        config: ScanConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> ScanReport: ...


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "queued"
    progress: float = 0.0
    total_candidates: int = 0
    total_scanned: int = 0
    total_signals: int = 0
    errors: int = 0
    skipped: int = 0
    error: str | None = None
    report: ScanReport | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def snapshot(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "total_candidates": self.total_candidates,
            "total_scanned": self.total_scanned,
            "total_signals": self.total_signals,
            "errors": self.errors,
            "skipped": self.skipped,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class ScreenJobRunner:
    def __init__(self, engine: ScanEngineLike | None = None, max_workers: int = 2) -> None:
        self._engine = engine or ScreenEngine()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="screen-job"
        )
        self._jobs: OrderedDict[str, JobState] = OrderedDict()
        self._lock = Lock()
        self._shutdown = False

    def submit(self, config: ScanConfig) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            if self._shutdown:
                raise RuntimeError("任务执行器已关闭")
            self._jobs[job_id] = JobState(job_id=job_id)
            self._executor.submit(self._run, job_id, config)
        return job_id

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job_id: str, config: ScanConfig) -> None:
        state = self.get(job_id)
        if state is None:
            return
        with self._lock:
            state.status = "running"

        def on_progress(current: int, total: int, outcome: ScanOutcome) -> None:
            with self._lock:
                state.progress = current / total if total else 1.0
                state.total_candidates = total
                state.total_scanned = current
                state.total_signals += outcome.result.match_count if outcome.result else 0
                state.errors += 1 if outcome.error_reason else 0
                state.skipped += 1 if outcome.skipped_reason else 0

        try:
            report = self._engine.scan(config, progress_callback=on_progress)
        except Exception:  # noqa: BLE001 - API receives a safe task-level error
            logger.exception("公式选股任务 %s 执行失败", job_id)
            with self._lock:
                state.status = "failed"
                state.error = "扫描任务失败，请检查数据目录和选股配置后重试"
                state.finished_at = time.time()
            return
        with self._lock:
            state.status = "completed"
            state.progress = 1.0
            state.total_candidates = report.total_candidates
            state.total_scanned = report.total_scanned
            state.total_signals = report.total_signals
            state.errors = report.errors
            state.skipped = report.skipped
            state.report = report
            state.finished_at = time.time()

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        self._executor.shutdown(wait=wait, cancel_futures=True)
