from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Instrument, MarketBar
from app.database.session import get_engine, get_session_factory
from app.main import app


HEADERS = {"X-Dashboard-Token": "admin-test"}
NOW = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "snapshot-api.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-test")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    get_settings.cache_clear(); get_engine.cache_clear()
    return TestClient(app)


def add_market(symbol="SOXL"):
    with get_session_factory()() as db:
        instrument = Instrument(symbol="US." + symbol, market="US", code=symbol, display_name=symbol)
        db.add(instrument); db.flush()
        db.add(MarketBar(
            instrument_id=instrument.id, symbol="US." + symbol, interval="1d",
            timestamp_utc=NOW, timestamp_market=NOW, trading_date="2026-07-31",
            open=10, high=11, low=9, close="10.5", volume=100,
            market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO",
        )); db.commit()


def create_portfolio_and_watch(api, symbol="SOXL"):
    portfolio = api.post("/internal/portfolios", headers=HEADERS, json={
        "user_id": "user-a", "name": "Main", "is_default": True,
    }).json()
    response = api.post(f"/internal/portfolios/{portfolio['id']}/watchlist", headers=HEADERS, json={"symbol": symbol})
    assert response.status_code == 200
    return portfolio


def test_snapshot_api_permission_list_detail_pagination(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        add_market("SOXL"); add_market("QQQ")
        assert api.get("/api/market-snapshots").status_code == 401
        listing = api.get("/api/market-snapshots?page=1&page_size=1", headers=HEADERS)
        assert listing.status_code == 200 and listing.json()["total"] == 2
        assert listing.json()["items"][0]["symbol"] == "QQQ"
        detail = api.get("/api/market-snapshots/SOXL", headers=HEADERS)
        assert detail.status_code == 200 and detail.json()["latest_price"] == "10.50000000"


def test_snapshot_api_filters_validation_404_and_empty(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/api/market-snapshots", headers=HEADERS).json()["total"] == 0
        assert api.get("/api/market-snapshots/UNKNOWN", headers=HEADERS).status_code == 404
        assert api.get("/api/market-snapshots", headers=HEADERS, params={"candidate_signal": "BAD"}).status_code == 422
        assert api.get("/api/market-snapshots", headers=HEADERS, params={"page_size": 201}).status_code == 422


def test_watchlist_snapshot_and_portfolio_permission(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        add_market(); portfolio = create_portfolio_and_watch(api)
        path = f"/api/watchlists/{portfolio['id']}/snapshots"
        assert api.get(path).status_code == 401
        response = api.get(path, headers=HEADERS)
        assert response.status_code == 200 and response.json()["items"][0]["watching"] == "WATCHING"
        assert api.get("/api/watchlists/999/snapshots", headers=HEADERS).status_code == 404


def test_snapshot_endpoints_are_read_only_and_schema_unchanged(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        add_market()
        with get_session_factory()() as db:
            before = {name: db.execute(__import__('sqlalchemy').text("select count(*) from " + name)).scalar_one()
                      for name in ("market_bars", "candidate_signals", "trade_plans", "portfolio_holdings")}
        api.get("/api/market-snapshots", headers=HEADERS)
        api.get("/api/market-snapshots/SOXL", headers=HEADERS)
        with get_session_factory()() as db:
            after = {name: db.execute(__import__('sqlalchemy').text("select count(*) from " + name)).scalar_one()
                     for name in before}
            tables = set(__import__('sqlalchemy').inspect(db.bind).get_table_names())
        assert before == after and "market_snapshots" not in tables


def test_snapshot_dashboard_pages_and_login_protection(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        add_market(); portfolio = create_portfolio_and_watch(api)
        assert api.get("/dashboard/market-snapshots", follow_redirects=False).status_code == 303
        for path, page in (
            ("/dashboard/market-snapshots", "market-snapshots"),
            ("/dashboard/market-snapshots/SOXL", "market-snapshot-detail"),
            (f"/dashboard/watchlists/{portfolio['id']}/snapshot", "watchlist-snapshot"),
        ):
            response = api.get(path, headers=HEADERS)
            assert response.status_code == 200 and f'data-page="{page}"' in response.text


def test_openapi_contains_read_only_snapshot_routes(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        paths = api.get("/openapi.json").json()["paths"]
        assert "/api/market-snapshots" in paths
        assert "/api/market-snapshots/{symbol}" in paths
        assert "/api/watchlists/{portfolio_id}/snapshots" in paths
        assert all(set(value) <= {"get"} for path, value in paths.items() if "snapshot" in path)


def test_symbol_overview_api_and_empty_related_objects(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        add_market("PLTR")
        assert api.get("/api/symbols/PLTR/overview").status_code == 401
        response = api.get("/api/symbols/PLTR/overview", headers=HEADERS)
        assert response.status_code == 200
        value = response.json()
        assert value["symbol"] == "PLTR"
        assert value["snapshot"]["latest_price"] == "10.50000000"
        assert value["related_objects"]["snapshot"]["available"] is True
        assert value["related_objects"]["ai"]["available"] is False
        assert api.get("/api/symbols/UNKNOWN/overview", headers=HEADERS).status_code == 404


def test_symbol_overview_dashboard_navigation_and_openapi(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        assert api.get("/dashboard/symbols/SOXL", follow_redirects=False).status_code == 303
        page = api.get("/dashboard/symbols/SOXL", headers=HEADERS)
        assert page.status_code == 200 and 'data-page="symbol-overview"' in page.text
        paths = api.get("/openapi.json").json()["paths"]
        assert "/api/symbols/{symbol}/overview" in paths
        assert "/internal/symbols/{symbol}/ai-analysis" not in paths


def test_symbol_overview_ai_entry_defaults_to_dry_run(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        add_market("SOXL")
        with get_session_factory()() as db:
            from app.database.models import TradePlan
            db.add(TradePlan(
                plan_id="plan-overview", symbol="SOXL", market="US",
                strategy_name="pullback_restrength", strategy_version="1.0.0",
                lifecycle_stage="PLAN", direction="LONG", timeframe="1d",
            )); db.commit()
        response = api.post(
            "/internal/symbols/SOXL/ai-analysis", headers=HEADERS, json={},
        )
        assert response.status_code == 200
        assert response.json()["dry_run"] is True
        with get_session_factory()() as db:
            from app.database.models import CompanionAnalysis
            assert db.query(CompanionAnalysis).count() == 0
