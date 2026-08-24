from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app

HEADERS = {"X-Dashboard-Token": "local-node-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "local-node.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "local-node-test")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    monkeypatch.setenv("UNIVERSE_AUTO_UPDATE_ENABLED", "false")
    monkeypatch.setenv("REALTIME_RUNTIME_ENABLED", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def test_local_node_endpoints_require_token(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        for path in ("/api/market-context", "/api/position/QQQ", "/api/signals/recent"):
            assert api.get(path).status_code == 401


def test_local_node_empty_read_models(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        market = api.get("/api/market-context", headers=HEADERS)
        assert market.status_code == 200
        assert market.json()["real_trading"] == "DISABLED"
        position = api.get("/api/position/QQQ", headers=HEADERS)
        assert position.status_code == 200
        assert position.json() == {"symbol": "QQQ", "paper_only": True, "items": [], "total": 0}
        signals = api.get("/api/signals/recent", headers=HEADERS)
        assert signals.status_code == 200
        assert signals.json()["items"] == []


def test_health_remains_available_for_tailscale_probe(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/health").status_code == 200
