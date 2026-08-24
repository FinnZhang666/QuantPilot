from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


HEADERS = {"X-Dashboard-Token": "qmr-backtest-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "qmr-backtest-api.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "qmr-backtest-test")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def test_qmr_backtest_read_api_auth_empty_and_404(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/qmr/backtest/runs").status_code == 401
        assert api.get("/qmr/backtest/runs", headers=HEADERS).json()["total"] == 0
        assert api.get("/qmr/backtest/runs/999", headers=HEADERS).status_code == 404


def test_qmr_backtest_internal_dry_run_hidden_and_non_writing(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        payload = {"start_time": "2020-01-01T00:00:00Z", "end_time": "2024-01-01T00:00:00Z",
                   "dry_run": True}
        response = api.post("/internal/qmr/backtest/runs", headers=HEADERS, json=payload)
        assert response.status_code == 200
        assert response.json()["run_id"] is None
        assert api.get("/qmr/backtest/runs", headers=HEADERS).json()["total"] == 0
        assert "/internal/qmr/backtest/runs" not in api.get("/openapi.json").json()["paths"]


def test_qmr_backtest_empty_real_run_is_research(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        payload = {"start_time": "2020-01-01T00:00:00Z", "end_time": "2024-01-01T00:00:00Z"}
        response = api.post("/internal/qmr/backtest/runs", headers=HEADERS, json=payload)
        assert response.status_code == 200
        row = api.get("/qmr/backtest/runs/1", headers=HEADERS).json()
        assert row["status"] == "SUCCESS"
        assert row["strategy_status"] == "RESEARCH"
        assert "幸存者偏差" in row["warnings_json"][0]


def test_qmr_backtest_dashboard(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/dashboard/qmr-backtest", headers=HEADERS).status_code == 200
