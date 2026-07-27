from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Instrument, RealtimeBar, RealtimeQuote, RealtimeTicker
from app.database.session import get_engine, get_session_factory
from app.main import app


def build_client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "realtime-api.db"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    api = TestClient(app)
    api.__enter__()
    with get_session_factory()() as db:
        instrument = Instrument(symbol="US.QQQ", market="US", code="QQQ", is_supported=True, support_status="SUPPORTED", support_message="可用")
        db.add(instrument)
        db.flush()
        base = datetime(2026, 7, 27, 13, 30, tzinfo=timezone.utc)
        db.add(RealtimeQuote(
            instrument_id=instrument.id, symbol="US.QQQ", timestamp_utc=base,
            timestamp_market=base, timestamp_beijing=base, last_price=Decimal("500"),
            market_session="REGULAR", data_source="MOOMOO",
        ))
        for index in range(1100):
            moment = base + timedelta(seconds=index)
            db.add(RealtimeTicker(
                instrument_id=instrument.id, symbol="US.QQQ",
                ticker_time_utc=moment, ticker_time_market=moment,
                price=Decimal("500"), volume=1, sequence=str(index),
                market_session="REGULAR", data_source="MOOMOO",
            ))
            db.add(RealtimeBar(
                instrument_id=instrument.id, symbol="US.QQQ", interval="1m",
                timestamp_utc=base + timedelta(minutes=index),
                timestamp_market=base + timedelta(minutes=index),
                trading_date="2026-07-27", open=Decimal("1"), high=Decimal("2"),
                low=Decimal("1"), close=Decimal("2"), volume=1, is_closed=True,
                market_session="REGULAR", data_source="MOOMOO",
            ))
        db.commit()
    return api


def test_latest_quote_api(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        response = api.get("/realtime/quotes/latest", params={"symbols": "US.QQQ"})
        assert response.status_code == 200
        assert response.json()[0]["last_price"].startswith("500")
    finally:
        api.__exit__(None, None, None)


def test_ticker_default_and_absolute_limits(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        assert len(api.get("/realtime/tickers", params={"symbol": "US.QQQ"}).json()) == 1000
        assert api.get("/realtime/tickers", params={"symbol": "US.QQQ", "limit": 5001}).status_code == 422
    finally:
        api.__exit__(None, None, None)


def test_bar_default_and_absolute_limits(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        assert len(api.get("/realtime/bars", params={"symbol": "US.QQQ"}).json()) == 1000
        assert api.get("/realtime/bars", params={"symbol": "US.QQQ", "limit": 5001}).status_code == 422
    finally:
        api.__exit__(None, None, None)


def test_bar_only_supports_one_minute_with_chinese_error(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        response = api.get("/realtime/bars", params={"symbol": "US.QQQ", "interval": "5m"})
        assert response.status_code == 422 and "仅支持1m" in response.text
    finally:
        api.__exit__(None, None, None)


def test_realtime_status_is_chinese(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        payload = api.get("/realtime/status").json()
        assert payload["status_text"] == "已停止"
    finally:
        api.__exit__(None, None, None)


def test_realtime_api_does_not_expose_secrets(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        text = api.get("/realtime/health").text.lower()
        assert "token" not in text and "account" not in text and "password" not in text
    finally:
        api.__exit__(None, None, None)
