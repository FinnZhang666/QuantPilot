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
    monkeypatch.setenv("PAPER_SCHEDULER_ENABLED", "false")
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
            "/api/system-paper/orders", "/api/system-paper/fills",
            "/api/system-paper/equity", "/api/system-paper/performance",
            "/api/system-paper/scoreboard", "/api/system-paper/runtime",
            "/api/system-paper/scheduler", "/api/system-paper/audit",
            "/api/telegram-preview/system-paper/account",
        ):
            response = api.get(path)
            assert response.status_code == 200, (path, response.text)
            lowered = response.text.lower()
            assert "telegram_bot_token" not in lowered
            assert "api_key" not in lowered
        account = api.get("/api/system-paper/account").json()
        assert account["paper_only"] is True and account["status"] == "NOT_INITIALIZED"
        preview = api.get("/api/telegram-preview/system-paper/account").json()
        assert preview["preview_equals_real"] is True


def test_runtime_mutations_require_admin_and_stay_internal(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.post("/api/system-paper/runtime/process-once").status_code == 401
        response = api.post(
            "/api/system-paper/runtime/process-once",
            headers={"X-Dashboard-Token": "phase4-admin"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"
        assert response.json()["jobs"]["paper_entry_evaluation"]["status"] == "SUCCESS"
        dry_run = api.post(
            "/internal/system-paper/dry-run", json={"max_entries": 3},
            headers={"X-Dashboard-Token": "phase4-admin"},
        )
        assert dry_run.status_code == 200
        assert dry_run.json()["result"]["dry_run"] is True
        assert api.post("/internal/system-paper/run-once", json={"max_entries": 3}).status_code == 401

        schema = api.get("/openapi.json").json()
        assert "/internal/system-paper/run-once" not in schema["paths"]
        assert "/api/system-paper/runtime/start" not in schema["paths"]
        assert "/api/system-paper/positions/{position_id}" in schema["paths"]
        assert schema["paths"]["/api/system-paper/fills"]["get"]["responses"]["200"]["content"]


def test_empty_position_detail_and_internal_close_errors(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/api/system-paper/positions/999").status_code == 404
        response = api.post(
            "/internal/system-paper/positions/999/close",
            json={"reason": "MANUAL_CLOSE"},
            headers={"X-Dashboard-Token": "phase4-admin"},
        )
        assert response.status_code == 404


def test_private_read_api_stays_authenticated(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path, public=False) as api:
        assert api.get("/api/system-paper/account").status_code == 401
        assert api.get(
            "/api/system-paper/account", headers={"X-Dashboard-Token": "phase4-admin"},
        ).status_code == 200
