from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Instrument, MarketBar
from app.database.session import get_engine, get_session_factory
from app.main import app


def build_client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'history-api.db'}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    api = TestClient(app)
    api.__enter__()
    with get_session_factory()() as db:
        instrument = Instrument(
            symbol="US.QQQ", market="US", code="QQQ", is_supported=True,
            support_status="SUPPORTED", support_message="可用"
        )
        db.add(instrument)
        db.flush()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        db.add_all([
            MarketBar(
                instrument_id=instrument.id, symbol="US.QQQ", interval="1m",
                timestamp_utc=base + timedelta(minutes=i),
                timestamp_market=base + timedelta(minutes=i),
                trading_date="2026-01-01", open=Decimal("1"), high=Decimal("2"),
                low=Decimal("1"), close=Decimal("2"), volume=1,
                market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO"
            )
            for i in range(1100)
        ])
        db.commit()
    return api


def test_api_default_1000_limit(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        response = api.get("/history/bars", params={"symbol": "US.QQQ", "interval": "1m"})
        assert response.status_code == 200
        assert len(response.json()) == 1000
    finally:
        api.__exit__(None, None, None)


def test_api_absolute_limit(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        response = api.get(
            "/history/bars", params={"symbol": "US.QQQ", "interval": "1m", "limit": 5001}
        )
        assert response.status_code == 422
    finally:
        api.__exit__(None, None, None)


def test_api_parameter_error_is_chinese(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        response = api.get(
            "/history/bars",
            params={"symbol": "US.QQQ", "interval": "1m", "timezone": "Mars/Unknown"},
        )
        assert response.status_code == 422
        assert "时区名称无效" in response.text
    finally:
        api.__exit__(None, None, None)


def test_api_returns_all_three_timezones(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        item = api.get(
            "/history/bars", params={"symbol": "US.QQQ", "interval": "1m", "limit": 1}
        ).json()[0]
        assert {"timestamp_utc", "timestamp_market", "timestamp_beijing"} <= set(item)
    finally:
        api.__exit__(None, None, None)
