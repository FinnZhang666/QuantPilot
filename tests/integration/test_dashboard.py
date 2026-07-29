from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Opportunity
from app.database.session import get_engine, get_session_factory
from app.main import app


def dashboard_client(monkeypatch, tmp_path, public=False):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "dashboard.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "secret-dashboard-token")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true" if public else "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    client = TestClient(app)
    client.__enter__()
    return client


def login(client):
    return client.post(
        "/dashboard/login", data={"token": "secret-dashboard-token"},
        follow_redirects=False,
    )


def add_opportunity():
    with get_session_factory()() as db:
        row = Opportunity(
            symbol="SOXL", timeframe="1m", direction="LONG",
            opportunity_type="PULLBACK_RESTRENGTH",
            strategy_name="pullback_restrength", strategy_version="1.0.0",
            status="DETECTED", score=83, confidence=90,
            detected_at=datetime.now(timezone.utc), bar_time=datetime.now(timezone.utc),
            entry_reference_price=Decimal("10.25"),
            feature_snapshot_json={"ema_20": "ok"},
            strategy_snapshot_json={"signal_type": "CANDIDATE_BUY"},
            notification_status="PENDING",
        )
        db.add(row)
        db.commit()
        return row.id


def test_dashboard_login_and_all_pages(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        assert client.get("/dashboard", follow_redirects=False).status_code == 303
        assert login(client).status_code == 303
        for path in (
            "/dashboard", "/dashboard/opportunities", "/dashboard/runtime",
            "/dashboard/market-regime", "/dashboard/candidates",
            "/dashboard/strategies", "/dashboard/data-quality",
            "/dashboard/reports", "/dashboard/development",
        ):
            response = client.get(path)
            assert response.status_code == 200
            assert "公司工作台" in response.text
    finally:
        client.__exit__(None, None, None)


def test_empty_summary_and_data_quality(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        summary = client.get("/api/dashboard/summary")
        assert summary.status_code == 200
        assert summary.json()["today"]["opportunities"] == 0
        quality = client.get("/api/dashboard/data-quality")
        assert quality.status_code == 200 and quality.json()["items"] == []
        strategies = client.get("/api/dashboard/strategy-summary").json()
        assert strategies["items"] == []
    finally:
        client.__exit__(None, None, None)


def test_opportunity_filter_and_detail(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        opportunity_id = add_opportunity()
        filtered = client.get("/api/opportunities", params={
            "symbol": "SOXL", "timeframe": "1m", "direction": "LONG",
            "strategy_name": "pullback_restrength", "min_score": 80,
        })
        assert filtered.status_code == 200 and filtered.json()["total"] == 1
        assert client.get("/api/opportunities", params={"min_score": 84}).json()["total"] == 0
        detail = client.get("/api/opportunities/%s" % opportunity_id).json()
        assert detail["feature_snapshot"]["ema_20"] == "ok"
        assert client.get("/dashboard/opportunities/%s" % opportunity_id).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_runtime_write_requires_admin(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        assert client.get("/api/runtime/status").status_code == 200
        assert client.post("/api/runtime/start").status_code == 401
        assert client.post("/api/runtime/stop").status_code == 401
    finally:
        client.__exit__(None, None, None)


def test_issue_crud_filters_and_auth(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path, public=True)
    try:
        payload = {
            "title": "检查数据延迟", "description": "SOXL一分钟数据延迟需要调查",
            "source_type": "ADMIN", "priority": "HIGH", "category": "DATA",
        }
        assert client.post("/api/development/issues", json=payload).status_code == 401
        headers = {"X-Dashboard-Token": "secret-dashboard-token"}
        created = client.post("/api/development/issues", json=payload, headers=headers)
        assert created.status_code == 200
        issue_id = created.json()["id"]
        changed = client.patch(
            "/api/development/issues/%s" % issue_id,
            json={"status": "INVESTIGATING"}, headers=headers,
        )
        assert changed.json()["status"] == "INVESTIGATING"
        filtered = client.get("/api/development/issues", params={
            "status": "INVESTIGATING", "source_type": "ADMIN", "priority": "HIGH",
        })
        assert filtered.json()["total"] == 1
        assert client.get("/api/development/issues/%s" % issue_id).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_tokens_not_leaked(monkeypatch, tmp_path):
    client = dashboard_client(monkeypatch, tmp_path)
    try:
        login(client)
        for path in ("/dashboard", "/api/dashboard/summary", "/api/runtime/status"):
            response = client.get(path)
            assert "secret-dashboard-token" not in response.text
            assert "telegram_bot_token" not in response.text
    finally:
        client.__exit__(None, None, None)
