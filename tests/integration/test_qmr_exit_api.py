from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


HEADERS = {"X-Dashboard-Token": "qmr-exit-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "qmr-exit.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "qmr-exit-test")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def test_qmr_exit_read_api_and_hidden_internal_run(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        response = api.get("/api/qmr/exit", headers=HEADERS)
        assert response.status_code == 200 and response.json() == {"items": [], "total": 0}
        run = api.post("/internal/qmr/exit/run?dry_run=true", headers=HEADERS)
        assert run.status_code == 200
        assert run.json()["scanned"] == 0
        assert "/internal/qmr/exit/run" not in api.get("/openapi.json").json()["paths"]


def test_qmr_exit_admin_required(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.post("/internal/qmr/exit/run").status_code == 401
        assert api.get("/api/qmr/exit/999", headers=HEADERS).status_code == 404


def test_real_auto_trading_cannot_be_enabled(monkeypatch):
    monkeypatch.setenv("REAL_AUTO_TRADING", "true")
    get_settings.cache_clear()
    try:
        get_settings()
        assert False, "real auto trading must fail closed"
    except ValueError as exc:
        assert "真实自动交易" in str(exc)
