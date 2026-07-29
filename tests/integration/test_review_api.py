from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Opportunity
from app.database.session import get_engine, get_session_factory
from app.main import app


def make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "review-api.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    client = TestClient(app)
    client.__enter__()
    return client


def seed():
    with get_session_factory()() as db:
        db.add(Opportunity(
            symbol="SOXL", timeframe="1d", direction="LONG",
            opportunity_type="TEST", strategy_name="pullback_restrength",
            strategy_version="1.0.0", status="ACTIVE", score=80,
            detected_at=datetime.now(timezone.utc), bar_time=datetime.now(timezone.utc),
            entry_reference_price=Decimal("100"), feature_snapshot_json={},
            strategy_snapshot_json={}, notification_status="PENDING",
        ))
        db.commit()


def test_review_api_requires_admin(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    try:
        assert client.get("/api/review/pending").status_code == 401
        assert client.post("/api/review/run").status_code == 401
    finally:
        client.__exit__(None, None, None)


def test_review_pending_run_and_dashboard(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    try:
        seed()
        headers = {"X-Dashboard-Token": "admin"}
        pending = client.get("/api/review/pending", headers=headers)
        assert pending.status_code == 200 and pending.json()["total"] == 1
        result = client.post("/api/review/run", headers=headers).json()
        assert result["failed"] == 1
        listing = client.get("/api/review", headers=headers).json()
        assert listing["total"] == 1
        review_id = listing["items"][0]["id"]
        assert client.get("/api/review/%s" % review_id, headers=headers).status_code == 200
        assert client.get("/dashboard/reviews", cookies={"dashboard_admin": "admin"}).status_code == 200
        assert client.get("/dashboard/reviews/%s" % review_id, cookies={"dashboard_admin": "admin"}).status_code == 200
        assert "telegram_bot_token" not in client.get(
            "/api/review/%s" % review_id, headers=headers,
        ).text.lower()
    finally:
        client.__exit__(None, None, None)
