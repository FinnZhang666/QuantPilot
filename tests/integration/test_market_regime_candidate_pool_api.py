from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import CandidatePoolEntry, CandidatePoolRun, MarketRegime
from app.database.session import get_engine, get_session_factory
from app.main import app


NOW = datetime.now(timezone.utc)


def client(monkeypatch, tmp_path, public=True):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "sprint09.db"))
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "admin-sprint09")
    monkeypatch.setenv("DASHBOARD_READONLY_PUBLIC", "true" if public else "false")
    get_settings.cache_clear()
    get_engine.cache_clear()
    api = TestClient(app)
    api.__enter__()
    return api


def seed():
    with get_session_factory()() as db:
        regime = MarketRegime(
            market="US", timeframe="1d", regime="BULL", trend_score=75,
            breadth_score=None, momentum_score=70, volatility_score=65,
            risk_score=60, long_bias=72, short_bias=38, confidence=84,
            benchmark_symbol="QQQ", sector_benchmark_symbol="SOXX",
            evaluated_at=NOW, bar_time=NOW, valid_until=NOW + timedelta(minutes=30),
            feature_snapshot_json={"QQQ": {"rsi_14": 60}},
            reason_snapshot_json={"reasons": ["趋势向上"], "risks": [], "data_sufficient": True},
        )
        db.add(regime)
        db.flush()
        entry = CandidatePoolEntry(
            symbol="SOXL", market="US", asset_type="ETF", direction="LONG",
            source_type="WATCHLIST", source_reference="WATCHLIST",
            pool_date=NOW.date().isoformat(), status="CANDIDATE",
            long_score=84, short_score=31, final_score=84, rank=1,
            market_regime_id=regime.id, benchmark_symbol="SOXX",
            sector_benchmark_symbol="SOXX",
            reason_snapshot_json={"reasons": ["趋势成立"], "risks": [], "sources": ["WATCHLIST"]},
            filter_snapshot_json={"trend": {"passed": True}},
            feature_snapshot_json={"ema20_vs_ema60_pct": 2},
            first_seen_at=NOW, last_seen_at=NOW, expires_at=NOW + timedelta(hours=36),
        )
        db.add(entry)
        db.add(CandidatePoolRun(
            run_type="MANUAL", market="US", started_at=NOW, completed_at=NOW,
            status="COMPLETED", universe_size=9, scanned_size=9, candidate_count=1,
            long_count=1, short_count=0, both_count=0, regime_id=regime.id,
            error_count=0, summary_json={"config_version": "1.0.0"},
        ))
        db.commit()
        return entry.id


def test_regime_api_and_dashboard(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        seed()
        current = api.get("/api/market-regime/current")
        assert current.status_code == 200 and current.json()["regime"] == "BULL"
        assert api.get("/api/market-regime/history", params={"limit": 1}).json()["total"] == 1
        assert api.get("/dashboard/market-regime").status_code == 200
    finally:
        api.__exit__(None, None, None)


def test_candidate_filters_pagination_detail_and_dashboard(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        entry_id = seed()
        result = api.get("/api/candidate-pool", params={
            "direction": "LONG", "source": "WATCHLIST", "status": "CANDIDATE",
            "min_score": 80, "limit": 1,
        }).json()
        assert result["total"] == 1 and result["items"][0]["symbol"] == "SOXL"
        assert api.get("/api/candidate-pool/%s" % entry_id).status_code == 200
        assert api.get("/api/candidate-pool/runs").json()["total"] == 1
        assert api.get("/dashboard/candidates").status_code == 200
        assert api.get("/dashboard/candidates/%s" % entry_id).status_code == 200
    finally:
        api.__exit__(None, None, None)


def test_write_auth_and_expire(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        entry_id = seed()
        assert api.post("/api/market-regime/evaluate").status_code == 401
        assert api.post("/api/candidate-pool/build").status_code == 401
        assert api.post("/api/candidate-pool/refresh").status_code == 401
        assert api.post("/api/candidate-pool/%s/expire" % entry_id).status_code == 401
        response = api.post(
            "/api/candidate-pool/%s/expire" % entry_id,
            headers={"X-Dashboard-Token": "admin-sprint09"},
        )
        assert response.status_code == 200 and response.json()["status"] == "EXPIRED"
    finally:
        api.__exit__(None, None, None)


def test_empty_database_and_tokens_not_leaked(monkeypatch, tmp_path):
    api = client(monkeypatch, tmp_path)
    try:
        assert api.get("/api/market-regime/current").json()["regime"] == "UNKNOWN"
        assert api.get("/api/candidate-pool").json()["items"] == []
        for path in ("/dashboard/market-regime", "/dashboard/candidates", "/api/dashboard/summary"):
            response = api.get(path)
            assert response.status_code == 200
            assert "admin-sprint09" not in response.text
            assert "telegram_bot_token" not in response.text
    finally:
        api.__exit__(None, None, None)
