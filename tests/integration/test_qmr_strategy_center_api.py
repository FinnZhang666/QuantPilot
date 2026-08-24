from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


HEADERS = {"X-Dashboard-Token": "strategy-center-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "strategy-center.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "strategy-center-test")
    monkeypatch.setenv("UNIVERSE_AUTO_UPDATE_ENABLED", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def test_qmr_strategy_api_detail_and_dashboard(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        listed = api.get("/api/strategy-center", headers=HEADERS)
        assert listed.status_code == 200
        assert listed.json()["items"][0]["strategy_code"] == "quality_mispricing_recovery"
        detail = api.get("/api/strategy-center/quality_mispricing_recovery", headers=HEADERS)
        assert detail.status_code == 200 and detail.json()["short_name"] == "QMR"
        assert api.get("/dashboard/strategies", headers=HEADERS).status_code == 200
        assert api.get("/dashboard/strategies/quality_mispricing_recovery", headers=HEADERS).status_code == 200


def test_qmr_enable_disable_is_admin_only_and_hidden(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        path = "/internal/strategy-center/quality_mispricing_recovery/disable"
        assert api.post(path).status_code == 401
        disabled = api.post(path, headers=HEADERS)
        assert disabled.status_code == 200 and disabled.json()["status"] == "DISABLED"
        enabled = api.post(path.replace("disable", "enable"), headers=HEADERS)
        assert enabled.status_code == 200 and enabled.json()["is_enabled"] is True
        assert path not in api.get("/openapi.json").json()["paths"]
