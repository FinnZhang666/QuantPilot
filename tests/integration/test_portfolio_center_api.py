from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


HEADERS = {"X-Dashboard-Token": "admin-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "portfolio-center-api.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def create_portfolio(api, name="My Portfolio", user="user-a"):
    response = api.post("/internal/portfolios", headers=HEADERS, json={
        "user_id": user, "name": name, "currency": "USD", "is_default": True,
    })
    assert response.status_code == 200
    return response.json()


def test_unknown_identity_fails_closed_and_internal_requires_admin(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/api/portfolios").status_code == 401
        assert api.post("/internal/portfolios", json={"user_id": "u", "name": "P"}).status_code == 401


def test_portfolio_crud_default_validation_and_public_read(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        first = create_portfolio(api)
        duplicate = api.post("/internal/portfolios", headers=HEADERS, json={"user_id": "user-a", "name": "my  portfolio"})
        assert duplicate.status_code == 409
        second = create_portfolio(api, "ETF")
        assert api.post(f"/internal/portfolios/{first['id']}/set-default", headers=HEADERS).status_code == 200
        rejected = api.patch(f"/internal/portfolios/{first['id']}", headers=HEADERS, json={"status": "INACTIVE"})
        assert rejected.status_code == 422
        listing = api.get("/api/portfolios?page_size=1", headers=HEADERS)
        assert listing.status_code == 200 and listing.json()["total"] == 2 and len(listing.json()["items"]) == 1
        assert api.get(f"/api/portfolios/{second['id']}", headers=HEADERS).status_code == 200


def test_holding_create_close_filters_decimal_and_detail(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        p = create_portfolio(api)
        opened = api.post(f"/internal/portfolios/{p['id']}/holdings", headers=HEADERS, json={
            "symbol": " soxl ", "market": "US", "direction": "LONG",
            "quantity": "1.12345678", "average_cost": "28.12345678",
        })
        assert opened.status_code == 200 and opened.json()["quantity"] == "1.12345678"
        holding_id = opened.json()["id"]
        listing = api.get(f"/api/portfolios/{p['id']}/holdings?symbol=SOXL", headers=HEADERS)
        assert listing.json()["total"] == 1
        assert api.get(f"/api/holdings/{holding_id}", headers=HEADERS).status_code == 200
        closed = api.post(f"/internal/holdings/{holding_id}/close", headers=HEADERS, json={"notes": "Manual"})
        assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"
        assert api.post(f"/internal/holdings/{holding_id}/close", headers=HEADERS, json={}).status_code == 422


def test_holding_validation_errors_are_not_500(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        p = create_portfolio(api)
        for payload in (
            {"symbol": "", "quantity": "1", "average_cost": "1"},
            {"symbol": "QQQ", "market": "XX", "quantity": "1", "average_cost": "1"},
            {"symbol": "QQQ", "quantity": "0", "average_cost": "1"},
            {"symbol": "QQQ", "quantity": "1", "average_cost": "-1"},
        ):
            assert api.post(f"/internal/portfolios/{p['id']}/holdings", headers=HEADERS, json=payload).status_code == 422


def test_watchlist_add_duplicate_order_delete_and_statistics(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        p = create_portfolio(api); path = f"/internal/portfolios/{p['id']}/watchlist"
        item = api.post(path, headers=HEADERS, json={"symbol": " pltr ", "market": "US"})
        assert item.status_code == 200 and item.json()["symbol"] == "PLTR"
        assert api.post(path, headers=HEADERS, json={"symbol": "PLTR"}).status_code == 409
        wid = item.json()["id"]
        assert api.patch(f"{path}/{wid}/order", headers=HEADERS, json={"display_order": 5}).json()["display_order"] == 5
        assert api.get(f"/api/portfolios/{p['id']}/watchlist", headers=HEADERS).json()["total"] == 1
        stats = api.get(f"/api/portfolios/{p['id']}/statistics", headers=HEADERS).json()
        assert stats["watchlist_count"] == 1 and stats["total_holdings"] == 0
        assert api.delete(f"{path}/{wid}", headers=HEADERS).status_code == 200


def test_openapi_dashboard_and_no_duplicate_pages(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        p = create_portfolio(api); paths = api.get("/openapi.json").json()["paths"]
        assert "/api/portfolios" in paths
        assert not any(path.startswith("/internal/portfolios") or path.startswith("/internal/holdings") for path in paths)
        page = api.get("/dashboard/portfolios", headers=HEADERS)
        detail = api.get(f"/dashboard/portfolios/{p['id']}", headers=HEADERS)
        assert page.status_code == 200 and 'data-page="portfolios"' in page.text
        assert detail.status_code == 200 and 'data-page="portfolio-detail"' in detail.text


def test_missing_resources_and_page_size_limit(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/api/portfolios/999", headers=HEADERS).status_code == 404
        assert api.get("/api/holdings/999", headers=HEADERS).status_code == 404
        assert api.get("/api/portfolios?page_size=201", headers=HEADERS).status_code == 422
