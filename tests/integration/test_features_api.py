from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import FeatureValueRecord, Instrument
from app.database.session import get_engine, get_session_factory
from app.main import app


def build_client(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "features-api.db"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    api = TestClient(app)
    api.__enter__()
    with get_session_factory()() as db:
        instrument = Instrument(symbol="US.QQQ", market="US", code="QQQ", is_supported=True, support_status="SUPPORTED", support_message="可用")
        db.add(instrument)
        db.flush()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(1100):
            db.add(FeatureValueRecord(
                instrument_id=instrument.id, symbol="US.QQQ", interval="1d",
                timestamp_utc=base + timedelta(days=index), feature_name="ema_20",
                feature_version="1.0.0", parameters_hash="hash",
                value_decimal=Decimal(index), quality_status="VALID",
                source_bar_timestamp=base + timedelta(days=index), data_source="MOOMOO",
            ))
        db.commit()
    return api


def test_feature_values_default_limit(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        assert len(api.get("/features/values", params={"symbol": "US.QQQ", "interval": "1d"}).json()) == 1000
    finally:
        api.__exit__(None, None, None)


def test_feature_values_absolute_limit(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        assert api.get("/features/values", params={"symbol": "US.QQQ", "interval": "1d", "limit": 5001}).status_code == 422
    finally:
        api.__exit__(None, None, None)


def test_feature_latest_chinese_quality(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        payload = api.get("/features/latest", params={"symbol": "US.QQQ", "interval": "1d"}).json()[0]
        assert payload["quality_text"] == "有效"
    finally:
        api.__exit__(None, None, None)


def test_feature_api_no_sensitive_information(monkeypatch, tmp_path):
    api = build_client(monkeypatch, tmp_path)
    try:
        text = api.get("/features/latest", params={"symbol": "US.QQQ", "interval": "1d"}).text.lower()
        assert "token" not in text and "password" not in text and "account" not in text
    finally:
        api.__exit__(None, None, None)
