from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


HEADERS = {"X-Dashboard-Token": "qmr-live-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "qmr-live-api.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "qmr-live-test")
    monkeypatch.setenv("UNIVERSE_AUTO_UPDATE_ENABLED", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def test_qmr_live_read_api_auth_empty_and_404(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/qmr/live-signals").status_code == 401
        response = api.get("/qmr/live-signals", headers=HEADERS)
        assert response.status_code == 200 and response.json()["total"] == 0
        assert api.get("/qmr/live-signals/UNKNOWN", headers=HEADERS).status_code == 404


def test_qmr_live_statistics_and_internal_routes(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        stats = api.get("/qmr/live-signals/statistics", headers=HEADERS)
        assert stats.status_code == 200 and stats.json()["performance"]["sample_count"] == 0
        run = api.post("/internal/qmr/live/run", headers=HEADERS, json={})
        assert run.status_code == 200 and run.json()["scanned"] == 0
        track = api.post("/internal/qmr/live/track", headers=HEADERS, json={})
        assert track.status_code == 200 and track.json()["scanned"] == 0
        paths = api.get("/openapi.json").json()["paths"]
        assert "/internal/qmr/live/run" not in paths


def test_qmr_live_dashboard_pages(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/dashboard/qmr-live", headers=HEADERS).status_code == 200
        assert api.get("/dashboard/qmr-live/QMR-20260814-001", headers=HEADERS).status_code == 200
