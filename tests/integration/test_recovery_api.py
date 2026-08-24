from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


HEADERS = {"X-Dashboard-Token": "recovery-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "recovery-api.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "recovery-test")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def test_recovery_api_auth_empty_validation_and_404(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/qmr/recovery").status_code == 401
        response = api.get("/qmr/recovery", headers=HEADERS)
        assert response.status_code == 200 and response.json()["total"] == 0
        assert api.get("/qmr/recovery/UNKNOWN", headers=HEADERS).status_code == 404
        assert api.get("/qmr/recovery", headers=HEADERS, params={"entry_status": "BUY"}).status_code == 422


def test_recovery_dashboard_routes_are_protected_and_render(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/dashboard/qmr", follow_redirects=False).status_code in (302, 303, 307)
        assert api.get("/dashboard/qmr", headers=HEADERS).status_code == 200
        assert api.get("/dashboard/qmr/SOXL", headers=HEADERS).status_code == 200


def test_recovery_internal_run_is_hidden_and_dry_run_default(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert "/internal/recovery/run" not in api.get("/openapi.json").json()["paths"]
        result = api.post("/internal/recovery/run", headers=HEADERS)
        assert result.status_code == 200
        assert result.json()["created"] == 0
