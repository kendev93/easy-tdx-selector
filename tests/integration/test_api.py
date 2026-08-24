from __future__ import annotations

import time
from pathlib import Path

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


def wait_for_done(client: TestClient, job_id: str) -> dict:
    for _ in range(50):
        response = client.get(f"/api/v1/formula-screen/jobs/{job_id}")
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
