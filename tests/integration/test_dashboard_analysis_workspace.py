from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Instrument, MarketBar
from app.database.session import get_engine, get_session_factory
from app.main import app


HEADERS = {"X-Dashboard-Token": "workspace-test"}


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "workspace.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "workspace-test")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return TestClient(app)


def add_market(symbol):
    now = datetime(2026, 8, 25, 20, 0, tzinfo=timezone.utc)
    with get_session_factory()() as db:
        instrument = Instrument(
            symbol="US." + symbol, market="US", code=symbol, display_name=symbol,
        )
        db.add(instrument)
        db.flush()
        db.add(MarketBar(
            instrument_id=instrument.id, symbol="US." + symbol, interval="1d",
            timestamp_utc=now, timestamp_market=now, trading_date="2026-08-25",
            open=100, high=103, low=99, close="102.5", volume=1000,
            market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO",
        ))
        db.commit()


def test_manual_analysis_is_not_restricted_to_qmr_universe(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        add_market("MANL")
        assert api.get("/api/dashboard/analysis/MANL").status_code == 401
        response = api.get("/api/dashboard/analysis/MANL", headers=HEADERS)
        assert response.status_code == 200
        value = response.json()
        assert value["symbol"] == "MANL"
        assert value["analysis_scope"] == "MANUAL_ANALYSIS"
        assert value["in_qmr_universe"] is False
        assert value["current_price"] == "102.50000000"
        assert value["data_status"] == "AVAILABLE"


def test_unknown_symbol_returns_auditable_empty_analysis(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        response = api.get("/api/dashboard/analysis/UNKNOWN", headers=HEADERS)
        assert response.status_code == 200
        value = response.json()
        assert value["analysis_scope"] == "MANUAL_ANALYSIS"
        assert value["status"] == "NO_DATA"
        assert value["data_status"] == "UNAVAILABLE"
        assert set(value["missing_sections"]) == {
            "quality_mispricing", "recovery", "buy_score", "money_flow", "exit",
        }


def test_leveraged_etf_analysis_identifies_underlying(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        response = api.get("/api/dashboard/analysis/SOXL", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["underlying"]["symbol"] == "SOXX"
        assert api.get(
            "/api/dashboard/analysis/APPX", headers=HEADERS,
        ).json()["underlying"]["symbol"] == "APP"


def test_workspace_assets_expose_quick_analysis_and_compact_modules(monkeypatch, tmp_path):
    with client(monkeypatch, tmp_path) as api:
        source = api.get("/dashboard/static/dashboard.js").text
        stylesheet = api.get("/dashboard/static/dashboard.css").text
        assert 'id="quick-analysis-form"' in source
        assert "current strategy opportunities" not in source.lower()
        assert "mergedOpportunities" in source
        assert "QMR 模拟盘" in source and "最近信号" in source
        assert ".workspace-search" in stylesheet
        assert ".health-strip" in stylesheet
