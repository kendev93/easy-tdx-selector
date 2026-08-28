from __future__ import annotations

import time
from pathlib import Path

from easy_tdx import SecurityBar
from easy_tdx.offline import append_daily_bars
from fastapi.testclient import TestClient

from selector_app.screening.models import ScanReport
from selector_app.web.app import create_app


class EmptyEngine:
    def scan(self, config, progress_callback=None):
        return ScanReport(
            total_candidates=0,
            total_scanned=0,
            total_signals=0,
            errors=0,
            skipped=0,
            results=(),
            failure_reasons={},
            skip_reasons={},
        )


def wait_for_done(
    client: TestClient,
    job_id: str,
    base_path: str = "/api/v1/formula-screen/jobs",
) -> dict:
    for _ in range(50):
        response = client.get(f"{base_path}/{job_id}")
        assert response.status_code == 200
        payload = response.json()["data"]
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def valid_payload(tmp_path: Path) -> dict:
    vipdoc = tmp_path / "vipdoc"
    (vipdoc / "sh" / "lday").mkdir(parents=True, exist_ok=True)
    return {
        "selected_signals": ["indicator_three.accumulation_zone"],
        "combine_mode": "at_least",
        "minimum_matches": 1,
        "universe": "all",
        "vipdoc_path": str(vipdoc),
        "workers": 1,
        "period": "daily",
    }


def test_metadata_returns_signals_modes_and_supported_markets() -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.get("/api/v1/formula-screen/metadata")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["indicators"]
    assert {mode["value"] for mode in data["combine_modes"]} == {"all", "any", "at_least"}
    assert data["supported_markets"] == ["SH", "SZ"]


def test_health_endpoint_is_lightweight_and_does_not_require_vipdoc() -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_signal_is_rejected_without_stack_trace(tmp_path: Path) -> None:
    payload = valid_payload(tmp_path)
    payload["selected_signals"] = ["unknown.signal"]

    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.post("/api/v1/formula-screen/jobs", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "Traceback" not in response.text


def test_custom_formula_parse_returns_parameters_and_outputs() -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.post(
            "/api/v1/formula-screen/parse",
            json={"formula_text": "N:=5; BREAKOUT:CROSS(C,REF(C,N));"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["parameters"][0]["name"] == "N"
    assert data["parameters"][0]["default"] == 5
    assert data["signals"][0]["id"] == "custom.breakout"
    assert data["values"][0]["id"] == "custom.n"


def test_custom_formula_unsafe_input_is_rejected(tmp_path: Path) -> None:
    payload = valid_payload(tmp_path)
    payload.update(
        {
            "formula_text": "X:__import__('os').system('id');",
            "selected_signals": ["custom.x"],
            "combine_mode": "any",
            "minimum_matches": None,
        }
    )

    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.post("/api/v1/formula-screen/jobs", json=payload)

    assert response.status_code == 422
    assert "Traceback" not in response.text


def test_invalid_combine_mode_and_missing_vipdoc_are_rejected(tmp_path: Path) -> None:
    payload = valid_payload(tmp_path)
    payload["combine_mode"] = "invalid"
    with TestClient(create_app(engine=EmptyEngine())) as client:
        invalid_mode = client.post("/api/v1/formula-screen/jobs", json=payload)
    assert invalid_mode.status_code == 422

    payload = valid_payload(tmp_path)
    payload["vipdoc_path"] = str(tmp_path / "does-not-exist")
    with TestClient(create_app(engine=EmptyEngine())) as client:
        missing_path = client.post("/api/v1/formula-screen/jobs", json=payload)
    assert missing_path.status_code == 422
    assert "不存在" in missing_path.json()["error"]["message"]


def test_job_creation_status_and_empty_results() -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        payload = {
            "selected_signals": ["indicator_three.accumulation_zone"],
            "combine_mode": "any",
            "universe": "all",
            "vipdoc_path": "/tmp",
            "workers": 1,
            "period": "daily",
        }
        create_response = client.post("/api/v1/formula-screen/jobs", json=payload)
        assert create_response.status_code == 202
        job_id = create_response.json()["data"]["job_id"]
        state = wait_for_done(client, job_id)
        assert state["status"] == "completed"
        result_response = client.get(f"/api/v1/formula-screen/jobs/{job_id}/results")

    assert result_response.status_code == 200
    assert result_response.json()["data"] == []


def test_unknown_job_uses_the_standard_error_envelope() -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.get("/api/v1/formula-screen/jobs/not-found")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "detail" not in response.json()


def test_market_sync_job_can_be_created_and_polled(tmp_path: Path, monkeypatch) -> None:
    class FakeMarketSync:
        def sync(self, config, progress_callback=None):
            if progress_callback:
                progress_callback(1, 1)
            return {
                "total_candidates": 1,
                "processed": 1,
                "updated_files": 1,
                "written_bars": 3,
                "errors": 0,
                "failure_reasons": {},
            }

    monkeypatch.setenv("SELECTOR_VIPDOC_PATH", str(tmp_path))
    with TestClient(create_app(engine=EmptyEngine(), market_sync=FakeMarketSync())) as client:
        response = client.post(
            "/api/v1/market-data/sync",
            json={"vipdoc_path": str(tmp_path)},
        )
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        for _ in range(50):
            status_response = client.get(f"/api/v1/market-data/sync/jobs/{job_id}")
            assert status_response.status_code == 200
            state = status_response.json()["data"]
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("market sync job did not finish")

    assert state["status"] == "completed"
    assert state["result"]["written_bars"] == 3


def test_market_sync_rejects_an_unavailable_data_directory(tmp_path: Path) -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.post(
            "/api/v1/market-data/sync",
            json={"vipdoc_path": str(tmp_path / "missing-vipdoc")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "data_directory_error"


def test_backtest_job_can_be_created_and_results_are_available(tmp_path: Path) -> None:
    class FakeBacktestService:
        def run(self, config, progress_callback=None):
            if progress_callback:
                progress_callback(1, 1)
            return {
                "market": "SH",
                "code": "600000",
                "bars": 5,
                "start_date": "2024-01-02",
                "end_date": "2024-01-06",
                "buy_signal": config.buy_signal,
                "sell_signal": config.sell_signal,
                "performance": {"total_return": 0.04, "end_value": 10400.0},
                "equity_curve": [],
                "trades": [],
                "positions": [],
                "diagnostic": None,
            }

    with TestClient(
        create_app(engine=EmptyEngine(), backtest_service=FakeBacktestService())
    ) as client:
        response = client.post(
            "/api/v1/backtests",
            json={
                "market": "SH",
                "code": "600000",
                "vipdoc_path": str(tmp_path),
                "buy_signal": "custom.buy",
                "sell_signal": "custom.sell",
                "formula_text": "BUY:C>10; SELL:C<10;",
                "start_date": "2024-01-02",
                "end_date": "2024-01-06",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        state = None
        for _ in range(50):
            status_response = client.get(f"/api/v1/backtests/{job_id}")
            assert status_response.status_code == 200
            state = status_response.json()["data"]
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("backtest job did not finish")
        results_response = client.get(f"/api/v1/backtests/{job_id}/results")

    assert state is not None
    assert state["status"] == "completed"
    assert state["result"] is None
    assert results_response.status_code == 200
    assert results_response.json()["data"]["code"] == "600000"


def test_backtest_default_service_reads_day_file_and_serializes_result(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    filepath = vipdoc / "sh/lday/sh600000.day"
    filepath.parent.mkdir(parents=True)
    append_daily_bars(
        filepath,
        [
            SecurityBar(
                open=float(close),
                close=float(close),
                high=float(close) + 0.5,
                low=float(close) - 0.5,
                vol=100_000,
                amount=float(close) * 100_000,
                year=2024,
                month=1,
                day=index,
                hour=0,
                minute=0,
            )
            for index, close in enumerate((10, 11, 12, 13, 14, 13, 12, 14, 15, 14), start=1)
        ],
        price_coeff=0.01,
        vol_coeff=0.01,
    )

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/backtests",
            json={
                "market": "SH",
                "code": "600000",
                "vipdoc_path": str(vipdoc),
                "buy_signal": "custom.buy",
                "sell_signal": "custom.sell",
                "formula_text": "BUY:C=11; SELL:C=14;",
                "start_date": "2024-01-02",
                "end_date": "2024-01-06",
                "initial_cash": 10_000,
                "commission": 0,
                "min_commission": 0,
                "stamp_tax": 0,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        state = wait_for_done(client, job_id, "/api/v1/backtests")
        results_response = client.get(f"/api/v1/backtests/{job_id}/results")

    assert state["status"] == "completed"
    payload = results_response.json()["data"]
    assert payload["code"] == "600000"
    assert payload["trades"][0]["date"] == "2024-01-03"
    assert payload["equity_curve"][-1]["date"] == "2024-01-06"


def test_backtest_rejects_same_buy_and_sell_signal(tmp_path: Path) -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.post(
            "/api/v1/backtests",
            json={
                "market": "SH",
                "code": "600000",
                "vipdoc_path": str(tmp_path),
                "buy_signal": "indicator_three.begin_zone",
                "sell_signal": "indicator_three.begin_zone",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_backtest_task_returns_a_safe_domain_error(tmp_path: Path) -> None:
    class FailingBacktestService:
        def run(self, config, progress_callback=None):
            raise ValueError("指定日期范围内没有可用日线数据")

    with TestClient(
        create_app(engine=EmptyEngine(), backtest_service=FailingBacktestService())
    ) as client:
        response = client.post(
            "/api/v1/backtests",
            json={
                "market": "SH",
                "code": "600000",
                "vipdoc_path": str(tmp_path),
                "buy_signal": "indicator_three.begin_zone",
                "sell_signal": "indicator_three.end_zone",
            },
        )
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        state = None
        for _ in range(50):
            state_response = client.get(f"/api/v1/backtests/{job_id}")
            state = state_response.json()["data"]
            if state["status"] == "failed":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("backtest job did not fail")

    assert state is not None
    assert state["error"] == "指定日期范围内没有可用日线数据"


def test_portfolio_backtest_job_can_be_created_and_polled(tmp_path: Path) -> None:
    class FakePortfolioService:
        def run(self, config, progress_callback=None):
            if progress_callback:
                progress_callback(2, 2)
            return {
                "universe": "all",
                "total_candidates": 2,
                "processed": 2,
                "skipped": 0,
                "errors": 0,
                "bars": 5,
                "start_date": "2024-01-02",
                "end_date": "2024-01-06",
                "max_positions": config.max_positions,
                "ranking_value": config.ranking_value,
                "rank_order": config.rank_order,
                "performance": {"total_return": 0.12},
                "equity_curve": [],
                "trades": [],
                "states": [],
                "ranking_events": [],
                "failure_reasons": {},
                "diagnostic": None,
            }

    with TestClient(
        create_app(
            engine=EmptyEngine(),
            portfolio_backtest_service=FakePortfolioService(),
        )
    ) as client:
        response = client.post(
            "/api/v1/portfolio-backtests",
            json={
                "vipdoc_path": str(tmp_path),
                "universe": "all",
                "selected_signals": ["custom.buy"],
                "combine_mode": "any",
                "ranking_value": "custom.rank",
                "max_positions": 2,
                "formula_text": "BUY:C>0; RANK:C;",
                "stop_loss_pct": 0.05,
                "fitness_filter_enabled": True,
                "fitness_min_score": 60,
                "fitness_min_trades": 3,
                "fitness_max_drawdown": 0.4,
            },
        )
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        state = wait_for_done(client, job_id, "/api/v1/portfolio-backtests")
        results_response = client.get(f"/api/v1/portfolio-backtests/{job_id}/results")

    assert state["status"] == "completed"
    assert state["result"] is None
    assert results_response.status_code == 200
    assert results_response.json()["data"]["max_positions"] == 2


def test_portfolio_backtest_requires_a_sell_rule(tmp_path: Path) -> None:
    with TestClient(create_app(engine=EmptyEngine())) as client:
        response = client.post(
            "/api/v1/portfolio-backtests",
            json={
                "vipdoc_path": str(tmp_path),
                "universe": "all",
                "selected_signals": ["indicator_three.begin_zone"],
                "combine_mode": "any",
                "ranking_value": "indicator_three.varo7",
                "max_positions": 2,
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unexpected_job_failure_does_not_expose_internal_stack_trace() -> None:
    class FailingEngine:
        def scan(self, config, progress_callback=None):
            raise RuntimeError("secret implementation detail")

    with TestClient(create_app(engine=FailingEngine())) as client:
        payload = {
            "selected_signals": ["indicator_three.accumulation_zone"],
            "combine_mode": "any",
            "universe": "all",
            "vipdoc_path": "/tmp",
            "workers": 1,
            "period": "daily",
        }
        response = client.post("/api/v1/formula-screen/jobs", json=payload)
        job_id = response.json()["data"]["job_id"]
        state = wait_for_done(client, job_id)

    assert state["status"] == "failed"
    assert "secret implementation detail" not in state["error"]
    assert "Traceback" not in str(state)
