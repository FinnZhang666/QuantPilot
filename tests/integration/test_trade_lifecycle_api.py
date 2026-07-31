from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import CandidateSignal
from app.database.session import get_engine, get_session_factory
from app.main import app


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "lifecycle-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def add_signal_and_plan():
    from app.trade_lifecycle.service import TradeLifecycleService
    with get_session_factory()() as db:
        signal = CandidateSignal(
            symbol="SOXL", market="US", timeframe="60m",
            bar_timestamp=datetime(2026, 7, 31, tzinfo=timezone.utc),
            strategy_name="pullback_restrength", strategy_version="1.0.0",
            parameters_hash="hash", signal_type="CANDIDATE_BUY", score=81,
            confidence=86, status="VALID", summary_zh="测试",
            reasons_json=[], risks_json=[], feature_refs_json={}, components_json={},
        )
        db.add(signal)
        db.commit()
        row, _ = TradeLifecycleService(db).create_from_signal(signal.id)
        return row.plan_id


def test_trade_plan_read_only_api(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        plan_id = add_signal_and_plan()
        listing = api.get("/api/trade-plans", params={"symbol": "SOXL"})
        assert listing.status_code == 200 and listing.json()["total"] == 1
        item = listing.json()["items"][0]
        assert item["plan_id"] == plan_id and item["buy_zone"]["lower"] is None
        detail = api.get("/api/trade-plans/" + plan_id)
        assert detail.status_code == 200 and detail.json()["lifecycle_stage"] == "DISCOVER"
        history = api.get("/api/trade-plans/%s/history" % plan_id)
        assert history.status_code == 200 and history.json()["items"][0]["source"] == "STRATEGY_ADAPTER"
        assert api.get("/api/trade-plans/missing").status_code == 404


def test_trade_plan_api_limits_and_stage_validation(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/api/trade-plans", params={"limit": 1001}).status_code == 422
        response = api.get("/api/trade-plans", params={"lifecycle_stage": "INVALID"})
        assert response.status_code == 422


def test_trade_plan_dashboard_and_openapi(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        page = api.get("/dashboard/trade-plans")
        assert page.status_code == 200 and 'data-page="trade-plans"' in page.text
        assert "Trade Plans" in page.text
        paths = api.get("/openapi.json").json()["paths"]
        assert "/api/trade-plans" in paths
        assert "/api/trade-plans/{plan_id}/history" in paths
        assert "/internal/trade-plans/generate" not in paths


def test_internal_generation_is_admin_only_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "runtime-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-test")
    get_settings.cache_clear()
    get_engine.cache_clear()
    with TestClient(app) as api:
        with get_session_factory()() as db:
            signal = CandidateSignal(
                symbol="SOXL", market="US", timeframe="60m",
                bar_timestamp=datetime(2026, 7, 31, tzinfo=timezone.utc),
                strategy_name="pullback_restrength", strategy_version="1.0.0",
                parameters_hash="api-hash", signal_type="CANDIDATE_BUY", score=82,
                confidence=87, status="VALID", summary_zh="测试",
                reasons_json=[], risks_json=[], feature_refs_json={}, components_json={},
            )
            db.add(signal)
            db.commit()
        assert api.post("/internal/trade-plans/generate", json={"limit": 10}).status_code == 401
        headers = {"X-Dashboard-Token": "admin-test"}
        first = api.post("/internal/trade-plans/generate", json={"limit": 10}, headers=headers)
        second = api.post("/internal/trade-plans/generate", json={"limit": 10}, headers=headers)
        assert first.status_code == 200 and first.json()["created"] == 1
        assert second.status_code == 200 and second.json()["scanned"] == 0
        plan_id = first.json()["plan_ids"][0]
        page = api.get("/dashboard/trade-plans/" + plan_id)
        assert page.status_code == 200 and 'data-page="trade-plan-detail"' in page.text
