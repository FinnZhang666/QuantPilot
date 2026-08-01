from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine, get_session_factory
from app.main import app
from app.paper_runtime.manager import RuntimeManager, replace_runtime_manager


def client(monkeypatch, tmp_path, public=True):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "paper-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true" if public else "false")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "phase4-admin")
    monkeypatch.setenv("RUNTIME_MANAGER_ENABLED", "true")
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("REVIEW_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_SCOREBOARD_ENABLED", "true")
    monkeypatch.setenv("REALTIME_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    monkeypatch.setenv("AI_COMPANION_ENABLED", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    settings = get_settings()
    replace_runtime_manager(RuntimeManager(settings, get_session_factory()))
    return TestClient(app)


def test_public_paper_read_api_and_telegram_preview(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        for path in (
            "/api/system-paper/account", "/api/system-paper/positions",
            "/api/system-paper/orders", "/api/system-paper/equity",
            "/api/system-paper/scoreboard", "/api/system-paper/runtime",
            "/api/telegram-preview/system-paper/account",
        ):
            response = api.get(path)
            assert response.status_code == 200
            assert "telegram_bot_token" not in response.text.lower()
        account = api.get("/api/system-paper/account").json()
        assert account["paper_only"] is True and account["status"] == "NOT_INITIALIZED"
        preview = api.get("/api/telegram-preview/system-paper/account").json()
        assert preview["preview_equals_real"] is True


def test_runtime_mutations_require_admin_and_process_without_external_transport(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.post("/api/system-paper/runtime/process-once").status_code == 401
        response = api.post(
            "/api/system-paper/runtime/process-once",
            headers={"X-Dashboard-Token": "phase4-admin"},
        )
        assert response.status_code == 200
        assert response.json()["paper"]["status"] == "SUCCESS"
        account = api.get("/api/system-paper/account").json()
        assert account["total_equity"] == account["initial_cash"]


def test_private_read_api_stays_authenticated(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path, public=False) as api:
        assert api.get("/api/system-paper/account").status_code == 401
        assert api.get(
            "/api/system-paper/account", headers={"X-Dashboard-Token": "phase4-admin"},
        ).status_code == 200
