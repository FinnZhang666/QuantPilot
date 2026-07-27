from pathlib import Path

from fastapi.testclient import TestClient

import app.api.moomoo as moomoo_api
from app.core.config import get_settings
from app.data.providers.moomoo import MoomooCapabilityReport
from app.database.session import get_engine
from app.main import app


class FakeManager:
    order_calls = 0

    def sdk_version(self):
        return "9.6.5608"

    def inspect(self, symbols, enabled=True):
        return MoomooCapabilityReport(
            enabled=enabled,
            sdk_available=True,
            sdk_version="9.6.5608",
            opend_reachable=True,
            opend_logged_in=True,
            quote_context_available=True,
            paper_account_found=True,
            live_account_found=True,
            status_code="connected",
            status_message_zh="OpenD连接和能力检查完成",
        )


def client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'moomoo-api.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    monkeypatch.setattr(moomoo_api, "_manager", lambda settings: FakeManager())
    return TestClient(app)


def test_opend_unreachable_does_not_break_fastapi(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/health").status_code == 200
        assert api.get("/moomoo/status").status_code == 200


def test_moomoo_status_does_not_leak_sensitive_data(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "do-not-leak-token")
    with client(monkeypatch, tmp_path) as api:
        body = api.get("/moomoo/status").text
        assert "do-not-leak-token" not in body
        assert "account_id" not in body
        assert "order_submission_enabled" in body


def test_moomoo_check_never_calls_order_api(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        response = api.post("/moomoo/check", json={"symbols": ["US.QQQ"]})
        assert response.status_code == 200
        assert response.json()["order_submission_enabled"] is False
        assert FakeManager.order_calls == 0
