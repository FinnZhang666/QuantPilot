from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine, get_session_factory
from app.main import app
from app.trade_lifecycle.domain import TradeDirection, TradePlanDraft
from app.trade_lifecycle.service import TradeLifecycleService


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "participation-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-test")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def create_plan():
    with get_session_factory()() as db:
        lifecycle = TradeLifecycleService(db)
        row = lifecycle.create(TradePlanDraft(
            symbol="SOXL", market="US", strategy_name="pullback_restrength",
            strategy_version="1.0.0", direction=TradeDirection.LONG,
            timeframe="60m", reference_price=Decimal("30"),
            stop_loss_price=Decimal("27"), target_prices=["33"],
        ))
        lifecycle.advance(row.plan_id, "PLAN", "策略确认", "TEST")
        return row.plan_id


def test_internal_open_close_auth_and_public_read(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        plan_id = create_plan()
        payload = {"user_id": "admin-1", "trade_plan_id": plan_id, "entry_price": "30.5"}
        assert api.post("/internal/user-positions/open", json=payload).status_code == 401
        headers = {"X-Dashboard-Token": "admin-test"}
        opened = api.post("/internal/user-positions/open", json=payload, headers=headers)
        assert opened.status_code == 200 and opened.json()["status"] == "OPEN"
        listing = api.get("/api/user-positions", params={"user_id": "admin-1"})
        assert listing.status_code == 200 and listing.json()["total"] == 1
        detail = api.get("/api/user-positions/%s" % opened.json()["id"])
        assert detail.json()["trade_plan"]["plan_id"] == plan_id
        closed = api.post("/internal/user-positions/close", json={
            "position_id": opened.json()["id"], "exit_price": "31.2",
        }, headers=headers)
        assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"
        stats = api.get("/api/user-positions/statistics").json()
        assert stats["closed_positions"] == 1 and stats["win_count"] == 1


def test_multiple_users_dashboard_and_hidden_internal_api(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        plan_id = create_plan()
        headers = {"X-Dashboard-Token": "admin-test"}
        ids = []
        for user in ("user-a", "user-b"):
            response = api.post("/internal/user-positions/open", json={
                "user_id": user, "trade_plan_id": plan_id, "entry_price": "30",
            }, headers=headers)
            ids.append(response.json()["id"])
        assert api.get("/api/user-positions").json()["total"] == 2
        page = api.get("/dashboard/positions")
        detail = api.get("/dashboard/positions/%s" % ids[0])
        assert page.status_code == 200 and 'data-page="positions"' in page.text
        assert detail.status_code == 200 and 'data-page="position-detail"' in detail.text
        paths = api.get("/openapi.json").json()["paths"]
        assert "/api/user-positions" in paths
        assert "/internal/user-positions/open" not in paths


def test_invalid_plan_and_duplicate_are_business_errors(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        headers = {"X-Dashboard-Token": "admin-test"}
        missing = api.post("/internal/user-positions/open", json={
            "user_id": "user", "trade_plan_id": "missing", "entry_price": "30",
        }, headers=headers)
        assert missing.status_code == 404 and "不存在" in missing.json()["detail"]
        plan_id = create_plan()
        payload = {"user_id": "user", "trade_plan_id": plan_id, "entry_price": "30"}
        assert api.post("/internal/user-positions/open", json=payload, headers=headers).status_code == 200
        duplicate = api.post("/internal/user-positions/open", json=payload, headers=headers)
        assert duplicate.status_code == 422 and "重复" in duplicate.json()["detail"]
