from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import get_engine
from app.main import app


def api_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "strategy-api.db"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    client = TestClient(app)
    client.__enter__()
    return client


def test_watchlist_api_crud_and_chinese_errors(monkeypatch, tmp_path):
    client = api_client(monkeypatch, tmp_path)
    try:
        created = client.post("/watchlist", json={"symbol": " pltr "})
        assert created.status_code == 200
        assert created.json()["symbol"] == "PLTR"
        assert client.post("/watchlist", json={"symbol": "PLTR"}).json()["result"] == "already_exists"
        assert client.get("/watchlist/NOPE").status_code == 404
        changed = client.patch("/watchlist/PLTR", json={"sector": "custom"}).json()
        assert changed["classification_source"] == "MANUAL"
        assert client.delete("/watchlist/PLTR").json()["enabled"] is False
        assert client.post("/watchlist/PLTR/enable").json()["enabled"] is True
    finally:
        client.__exit__(None, None, None)


def test_watchlist_api_pagination_and_filters(monkeypatch, tmp_path):
    client = api_client(monkeypatch, tmp_path)
    try:
        for symbol in ("QQQ", "SOXX", "SOXL"):
            client.post("/watchlist", json={"symbol": symbol})
        payload = client.get("/watchlist", params={"limit": 2, "offset": 1}).json()
        assert payload["total"] == 3
        assert len(payload["items"]) == 2
        assert client.get("/watchlist", params={"limit": 1001}).status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_parameters_api(monkeypatch, tmp_path):
    client = api_client(monkeypatch, tmp_path)
    try:
        client.post("/watchlist", json={"symbol": "SOXL"})
        before = client.get("/watchlist/SOXL/parameters").json()
        changed = client.patch("/watchlist/SOXL/parameters", json={
            "parameters": {"pullback_min_pct": 4.0},
        })
        assert changed.status_code == 200
        assert changed.json()["parameters_hash"] != before["parameters_hash"]
        assert client.patch("/watchlist/SOXL/parameters", json={
            "parameters": {"unknown": 1},
        }).status_code == 400
    finally:
        client.__exit__(None, None, None)


def test_strategy_calculate_dry_run_and_business_errors(monkeypatch, tmp_path):
    client = api_client(monkeypatch, tmp_path)
    try:
        client.post("/watchlist", json={"symbol": "SOXL"})
        response = client.post("/strategy/calculate", json={
            "symbols": ["SOXL"], "timeframes": ["1d"],
            "mode": "incremental", "dry_run": True,
        })
        assert response.status_code == 200
        assert response.json()["dry_run"] is True
        missing = client.post("/strategy/calculate", json={
            "symbols": ["NOPE"], "timeframes": ["1d"], "dry_run": True,
        })
        assert missing.status_code == 404
        invalid = client.post("/strategy/calculate", json={
            "symbols": ["SOXL"], "timeframes": ["1d"], "mode": "full",
        })
        assert invalid.status_code == 400
        assert "必须指定" in invalid.json()["detail"]
    finally:
        client.__exit__(None, None, None)


def test_strategy_list_limits_and_summary(monkeypatch, tmp_path):
    client = api_client(monkeypatch, tmp_path)
    try:
        assert client.get("/strategy/signals").json()["limit"] == 100
        assert client.get("/strategy/signals", params={"limit": 1001}).status_code == 422
        assert client.get("/strategy/runs").json()["limit"] == 100
        assert client.get("/strategy/runs", params={"limit": 1001}).status_code == 422
        assert "signal_type_counts" in client.get("/strategy/signals/summary").json()
    finally:
        client.__exit__(None, None, None)


def test_strategy_api_does_not_leak_secrets(monkeypatch, tmp_path):
    client = api_client(monkeypatch, tmp_path)
    try:
        text = client.get("/watchlist").text.lower()
        assert "password" not in text
        assert "telegram_bot_token" not in text
        assert "account_id" not in text
    finally:
        client.__exit__(None, None, None)
