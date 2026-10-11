from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import (
    Instrument, RealtimeBar, RealtimeQuote, RealtimeServiceStatus, RealtimeTicker,
)
from app.database.session import get_engine, get_session_factory
from app.main import app
from app.realtime.factory import replace_realtime_manager


def build_client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "realtime-api.db"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    replace_realtime_manager(None)
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
            prev_close=Decimal("490"), bid_price=Decimal("500.10"),
            ask_price=Decimal("500.20"), volume=123,
            market_session="REGULAR", data_source="MOOMOO",
        ))
        db.add(RealtimeQuote(
            instrument_id=instrument.id, symbol="US.QQQ",
            timestamp_utc=base + timedelta(seconds=1),
            timestamp_market=base + timedelta(seconds=1),
            timestamp_beijing=base + timedelta(seconds=1),
            last_price=Decimal("501"), prev_close=Decimal("490"),
            market_session="REGULAR", data_source="MOOMOO",
        ))
        status = db.query(RealtimeServiceStatus).filter_by(service_name="moomoo_realtime").one_or_none()
        if status is None:
            status = RealtimeServiceStatus(service_name="moomoo_realtime")
            db.add(status)
        status.status = "CONNECTED"
        status.subscribed_symbols_json = ["US.QQQ"]
        status.subscribed_types_json = ["QUOTE"]
        status.last_message_at = base + timedelta(seconds=1)
        status.metadata_json = {"received": 2, "persisted": 2, "market_session": "REGULAR"}
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
        assert response.json()[0]["last_price"].startswith("501")
        assert response.json()[0]["change_pct"] > 0
        assert api.get("/realtime/quotes/latest").json()[0]["symbol"] == "US.QQQ"
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
        assert payload["status_text"] == "已连接"
    finally:
        api.__exit__(None, None, None)


def test_realtime_api_does_not_expose_secrets(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        text = api.get("/realtime/health").text.lower()
        assert api.get("/realtime/health").json()["status"] == "CONNECTED"
        assert "token" not in text and "account" not in text and "password" not in text
    finally:
        api.__exit__(None, None, None)
