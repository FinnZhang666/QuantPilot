from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app
from app.telegram_runtime.runtime import reset_telegram_runtime


def client(monkeypatch, tmp_path, public=True):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "telegram-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true" if public else "false")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "phase5-admin")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("AI_COMPANION_ENABLED", "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    reset_telegram_runtime()
    return TestClient(app)


def test_public_runtime_registry_preview_feedback_and_statistics(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        for path in (
            "/api/telegram/runtime", "/api/telegram/bots",
            "/api/telegram/statistics", "/api/telegram/feedback",
            "/api/telegram/preview/trade_companion_zh/welcome",
            "/api/telegram/preview/trade_companion_en/more",
        ):
            response = api.get(path)
            assert response.status_code == 200, (path, response.text)
            lowered = response.text.lower()
            assert "telegram_bot_token" not in lowered
            assert "gemini_api_key" not in lowered
            assert "aiza" not in lowered
        bots = api.get("/api/telegram/bots").json()
        assert bots["total"] == 5 and bots["secrets_exposed"] is False
        preview = api.get("/api/telegram/preview/trade_companion_zh/welcome").json()
        assert preview["preview_equals_real"] is True
        assert "陪你走过每一次交易" in preview["text"]


def test_sync_dry_run_is_admin_only_and_hidden_from_openapi(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.post("/internal/telegram/sync", json={"dry_run": True}).status_code == 401
        response = api.post(
            "/internal/telegram/sync", json={"dry_run": True},
            headers={"X-Dashboard-Token": "phase5-admin"},
        )
        assert response.status_code == 200
        assert response.json()["total"] == 5
        assert all(item["avatar"] == "MANUAL_REQUIRED" for item in response.json()["items"])
        schema = api.get("/openapi.json").json()
        assert "/internal/telegram/sync" not in schema["paths"]
        assert "/api/telegram/runtime" in schema["paths"]


def test_private_read_api_requires_dashboard_admin(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path, public=False) as api:
        assert api.get("/api/telegram/bots").status_code == 401
        assert api.get(
            "/api/telegram/bots", headers={"X-Dashboard-Token": "phase5-admin"},
        ).status_code == 200
