from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine, get_session_factory
from app.main import app
from app.trade_lifecycle.domain import TradeDirection, TradePlanDraft
from app.trade_lifecycle.service import TradeLifecycleService


def client(monkeypatch, tmp_path, enabled=True):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "companion-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("AI_COMPANION_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("AI_COMPANION_PROVIDER", "mock")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def create_plan():
    with get_session_factory()() as db:
        lifecycle = TradeLifecycleService(db)
        row = lifecycle.create(TradePlanDraft(
            symbol="SOXL", market="US", strategy_name="pullback_restrength",
            strategy_version="1.0.0", direction=TradeDirection.LONG,
            timeframe="60m", reference_price=Decimal("100"), score=80,
        ))
        lifecycle.advance(row.plan_id, "PLAN", "策略确认", "TEST")
        return row.plan_id


def test_internal_api_defaults_dry_run_and_requires_admin(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        plan_id = create_plan()
        path = "/internal/companion/trade-plans/%s/generate" % plan_id
        assert api.post(path, json={}).status_code == 401
        headers = {"X-Dashboard-Token": "admin-test"}
        dry = api.post(path, json={}, headers=headers)
        assert dry.status_code == 200 and dry.json()["dry_run"] is True
        assert api.get("/api/companion-analyses").json()["total"] == 0
        paths = api.get("/openapi.json").json()["paths"]
        assert path not in paths and "/api/companion-analyses" in paths


def test_write_cache_force_read_api_and_dashboard(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        plan_id = create_plan()
        path = "/internal/companion/trade-plans/%s/generate" % plan_id
        headers = {"X-Dashboard-Token": "admin-test"}
        first = api.post(path, json={"dry_run": False}, headers=headers)
        cached = api.post(path, json={"dry_run": False}, headers=headers)
        forced = api.post(path, json={"dry_run": False, "force": True}, headers=headers)
        assert first.status_code == 200 and first.json()["analysis"]["status"] == "COMPLETED"
        assert cached.json()["cached"] is True and forced.json()["cached"] is False
        listing = api.get("/api/companion-analyses", params={
            "context_type": "TRADE_PLAN", "provider": "mock", "limit": 10,
        })
        assert listing.status_code == 200 and listing.json()["total"] == 2
        item = listing.json()["items"][0]
        assert "context_snapshot" not in item and "api_key" not in str(item).lower()
        detail = api.get("/api/companion-analyses/%s" % item["id"])
        assert detail.status_code == 200 and detail.json()["source"]["symbol"] == "SOXL"
        page = api.get("/dashboard/companion")
        page_detail = api.get("/dashboard/companion/%s" % item["id"])
        assert page.status_code == 200 and 'data-page="companion"' in page.text
        assert page_detail.status_code == 200 and 'data-page="companion-detail"' in page_detail.text


def test_unified_statistics_preview_and_alias_routes(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        headers = {"X-Dashboard-Token": "admin-test"}
        response = api.post("/internal/ai-companion/generate", json={
            "object_type": "STATISTICS",
        }, headers=headers)
        assert response.status_code == 200 and response.json()["template_id"] == "STATISTICS_EXPLANATION"
        assert api.get("/api/ai-companion/outputs").status_code == 200
        assert api.get("/dashboard/ai-companion").status_code == 200
        paths = api.get("/openapi.json").json()["paths"]
        assert "/internal/ai-companion/generate" not in paths


def test_disabled_write_is_safe_business_error(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path, enabled=False) as api:
        plan_id = create_plan()
        response = api.post(
            "/internal/companion/trade-plans/%s/generate" % plan_id,
            json={"dry_run": False}, headers={"X-Dashboard-Token": "admin-test"},
        )
        assert response.status_code == 422 and "未启用" in response.json()["detail"]
        assert api.get("/api/companion-analyses").json()["total"] == 0


def test_api_pagination_and_missing_object(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        headers = {"X-Dashboard-Token": "admin-test"}
        missing = api.post(
            "/internal/companion/trade-plans/missing/generate",
            json={}, headers=headers,
        )
        assert missing.status_code == 404 and "不存在" in missing.json()["detail"]
        assert api.get("/api/companion-analyses", params={"limit": 1001}).status_code == 422
