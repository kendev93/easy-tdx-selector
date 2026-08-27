from __future__ import annotations

import time

from selector_app.screening.jobs import ScreenJobRunner, TaskUserError


def wait_until_complete(runner: ScreenJobRunner, job_id: str) -> None:
    for _ in range(100):
        state = runner.get(job_id)
        if state is not None and state.status == "completed":
            return
        time.sleep(0.005)
    raise AssertionError("job did not finish")


def test_runner_evicts_old_completed_results_but_keeps_latest() -> None:
    runner = ScreenJobRunner(max_results=1)
    try:
        first = runner.submit_callable(lambda _progress: {"value": 1}, description="test")
        wait_until_complete(runner, first)
        second = runner.submit_callable(lambda _progress: {"value": 2}, description="test")
        wait_until_complete(runner, second)

        assert runner.get(first) is None
        assert runner.get(second) is not None
    finally:
        runner.shutdown()


def test_runner_preserves_safe_user_error_for_background_tasks() -> None:
    runner = ScreenJobRunner(max_results=1)
    try:

        def fail(_progress):
            raise TaskUserError("日期范围内没有可用行情")

        job_id = runner.submit_callable(fail, description="历史回测")
        for _ in range(100):
            state = runner.get(job_id)
            if state is not None and state.status == "failed":
                break
            time.sleep(0.005)
        else:
            raise AssertionError("job did not fail")

        assert state is not None
        assert state.error == "日期范围内没有可用行情"
    finally:
        runner.shutdown()
