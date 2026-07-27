from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.init import create_schema
from app.database.session import get_engine
from app.main import app


def test_health_and_safe_config(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:AAxxxxxxxxxxxxxxxx")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "secret-chat")
    get_settings.cache_clear()
    get_engine.cache_clear()
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["live_trading"] == "blocked"
        config = client.get("/system/config")
        body = config.text
        assert "123456789:AAxxxxxxxxxxxxxxxx" not in body
        assert "secret-chat" not in body
        assert "telegram_bot_token" not in body
