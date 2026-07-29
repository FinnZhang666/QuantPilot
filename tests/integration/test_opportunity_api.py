from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Opportunity
from app.database.session import get_engine, get_session_factory
from app.main import app
from app.runtime.realtime_runtime import replace_runtime


class FakeRuntime:
    def __init__(self):
        self.status = "STOPPED"
        self.started = 0
        self.stopped = 0

    def snapshot(self, idempotent=False):
        return {
            "status": self.status, "status_text": "运行中" if self.status == "RUNNING" else "已停止",
            "opend_connected": False, "last_market_message_at": None,
            "last_strategy_run_at": None, "processed_count": 0, "error_count": 0,
            "thread_alive": self.status == "RUNNING", "idempotent": idempotent,
        }

    def start(self):
        if self.status == "RUNNING":
            return self.snapshot(True)
        self.started += 1
        self.status = "RUNNING"
        return self.snapshot()

    def stop(self):
        if self.status == "STOPPED":
            return self.snapshot(True)
        self.stopped += 1
        self.status = "STOPPED"
        return self.snapshot()


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "opportunity-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "test-admin")
    get_settings.cache_clear()
    get_engine.cache_clear()
    runtime = FakeRuntime()
    replace_runtime(runtime)
    api = TestClient(app)
    api.__enter__()
    return api, runtime


def test_opportunity_api_and_limit(monkeypatch, tmp_path):
    api, _ = client(monkeypatch, tmp_path)
    try:
        with get_session_factory()() as db:
            db.add(Opportunity(
                symbol="SOXL", timeframe="1m", direction="LONG",
                opportunity_type="PULLBACK_RESTRENGTH",
                strategy_name="pullback_restrength", strategy_version="1.0.0",
                status="DETECTED", score=83, confidence=90,
                detected_at=datetime.now(timezone.utc), bar_time=datetime.now(timezone.utc),
                entry_reference_price=Decimal("10"), feature_snapshot_json={"ema": "ok"},
                strategy_snapshot_json={"signal_type": "CANDIDATE_BUY"},
                notification_status="PENDING",
            ))
            db.commit()
        payload = api.get("/api/opportunities").json()
        assert payload["total"] == 1 and payload["items"][0]["feature_snapshot"]["ema"] == "ok"
        assert api.get("/api/opportunities/symbol/SOXL").status_code == 200
        assert api.get("/api/opportunities", params={"limit": 1001}).status_code == 422
        assert api.get("/api/opportunities/999").status_code == 404
    finally:
        api.__exit__(None, None, None)
        replace_runtime(None)


def test_runtime_api_start_stop_idempotent(monkeypatch, tmp_path):
    api, runtime = client(monkeypatch, tmp_path)
    try:
        headers = {"X-Dashboard-Token": "test-admin"}
        first = api.post("/api/runtime/start", headers=headers).json()
        second = api.post("/api/runtime/start", headers=headers).json()
        assert first["status"] == "RUNNING" and second["idempotent"]
        assert runtime.started == 1
        api.post("/api/runtime/stop", headers=headers)
        stopped = api.post("/api/runtime/stop", headers=headers).json()
        assert stopped["idempotent"] and runtime.stopped == 1
        status = api.get("/api/runtime/status")
        assert status.status_code == 200
        assert "telegram_bot_token" not in status.text
    finally:
        api.__exit__(None, None, None)
        replace_runtime(None)
