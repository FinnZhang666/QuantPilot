from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine, get_session_factory
from app.main import app
from tests.unit.test_trade_review_engine import add_bars, end_system_plan


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "trade-review-api.db"))
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-test")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def seed():
    with get_session_factory()() as db:
        add_bars(db)
        end_system_plan(db)


def test_generate_defaults_to_dry_run_and_requires_admin(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        seed()
        assert api.post("/internal/reviews/generate", json={}).status_code == 401
        headers = {"X-Dashboard-Token": "admin-test"}
        dry = api.post("/internal/reviews/generate", json={}, headers=headers)
        assert dry.status_code == 200 and dry.json()["dry_run"] is True
        assert api.get("/api/reviews").json()["total"] == 0
        write = api.post("/internal/reviews/generate", json={"dry_run": False}, headers=headers)
        assert write.status_code == 200 and write.json()["created"] == 1
        repeat = api.post("/internal/reviews/generate", json={"dry_run": False}, headers=headers)
        assert repeat.json()["updated"] == 1 and api.get("/api/reviews").json()["total"] == 1


def test_review_read_api_dashboard_and_statistics(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        seed()
        headers = {"X-Dashboard-Token": "admin-test"}
        api.post("/internal/reviews/generate", json={"dry_run": False}, headers=headers)
        listing = api.get("/api/reviews", params={"symbol": "SOXL", "review_type": "SYSTEM"})
        item = listing.json()["items"][0]
        assert item["result"] == "WIN" and item["mfe"] == "10.00000000"
        assert api.get("/api/reviews/%s" % item["id"]).status_code == 200
        assert api.get("/api/reviews/statistics").json()["system"]["wins"] == 1
        page = api.get("/dashboard/trade-reviews")
        detail = api.get("/dashboard/trade-reviews/%s" % item["id"])
        assert page.status_code == 200 and 'data-page="trade-reviews"' in page.text
        assert detail.status_code == 200 and 'data-page="trade-review-detail"' in detail.text
        paths = api.get("/openapi.json").json()["paths"]
        assert "/api/reviews" in paths and "/internal/reviews/generate" not in paths


def test_generate_filters_and_validation(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        seed()
        headers = {"X-Dashboard-Token": "admin-test"}
        empty = api.post("/internal/reviews/generate", json={"symbol": "QQQ"}, headers=headers)
        assert empty.status_code == 200 and empty.json()["scanned"] == 0
        invalid = api.post("/internal/reviews/generate", json={
            "start_time": "2026-08-02T00:00:00Z", "end_time": "2026-08-01T00:00:00Z",
        }, headers=headers)
        assert invalid.status_code == 422 and "不能晚于" in invalid.json()["detail"]
