from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Opportunity, OpportunityReview
from app.database.session import get_engine, get_session_factory
from app.main import app


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "ai-review.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    monkeypatch.setenv("AI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("AI_REVIEW_PROVIDER", "mock")
    get_settings.cache_clear()
    get_engine.cache_clear()
    value = TestClient(app)
    value.__enter__()
    return value


def seed():
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    with get_session_factory()() as db:
        opportunity = Opportunity(
            symbol="SOXL", timeframe="1d", direction="LONG",
            opportunity_type="TEST", strategy_name="pullback_restrength",
            strategy_version="1.0.0", status="REVIEWED", score=80,
            detected_at=now, bar_time=now, entry_reference_price=Decimal("100"),
            feature_snapshot_json={}, strategy_snapshot_json={},
            notification_status="NOTIFIED",
        )
        db.add(opportunity)
        db.flush()
        db.add(OpportunityReview(
            opportunity_id=opportunity.id, review_status="REVIEWED", review_time=now,
            holding_bars=20, holding_minutes=100, holding_days=1,
            entry_reference_price=100, exit_reference_price=105, last_price=105,
            mfe_percent=8, mae_percent=-2, return_percent=5,
            max_close_return=6, min_close_return=-1, expired=True,
            review_window="20d",
            price_path_json=[{"timestamp": now.isoformat(), "close": "105"}],
            statistics_json={"window_returns": {"20d": "5"}}, reason_json={},
        ))
        db.commit()


def test_ai_review_api_admin_and_run(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        seed()
        assert api.get("/api/ai-review/pending").status_code == 401
        headers = {"X-Dashboard-Token": "admin"}
        assert api.get("/api/ai-review/pending", headers=headers).json()["total"] == 1
        result = api.post("/api/ai-review/run", headers=headers, json={"limit": 20}).json()
        assert result["completed"] == 1
        listing = api.get("/api/ai-review", headers=headers).json()
        assert listing["total"] == 1 and listing["items"][0]["is_mock"]
        detail = api.get("/api/ai-review/1", headers=headers)
        assert detail.status_code == 200 and "api_key" not in detail.text.lower()
    finally:
        api.__exit__(None, None, None)


def test_ai_review_statistics_excludes_mock(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        seed()
        headers = {"X-Dashboard-Token": "admin"}
        api.post("/api/ai-review/run", headers=headers, json={"limit": 20})
        stats = api.get("/api/ai-review/statistics", headers=headers).json()
        assert stats["total_analyses"] == 0 and stats["mock_excluded"]
    finally:
        api.__exit__(None, None, None)


def test_ai_review_dashboard_pages(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        cookies = {"dashboard_admin": "admin"}
        assert api.get("/dashboard/ai-reviews", cookies=cookies).status_code == 200
        assert api.get("/dashboard/ai-reviews/1", cookies=cookies).status_code == 200
        assert "AI Review Analyst" in api.get("/dashboard/ai-reviews", cookies=cookies).text
    finally:
        api.__exit__(None, None, None)


def test_empty_database_generates_no_fake_data(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        headers = {"X-Dashboard-Token": "admin"}
        result = api.post("/api/ai-review/run", headers=headers, json={"limit": 20}).json()
        assert result["scanned"] == 0 and result["completed"] == 0
    finally:
        api.__exit__(None, None, None)
