from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.database.models import (
    Instrument, MarketBar, Opportunity, OpportunityReview, ReviewStatistic,
)
from app.review.config import load_review_windows, parse_window
from app.review.metrics import calculate_metrics, directional_return
from app.review.service import OpportunityReviewService
from app.core.config import Settings
from app.notifications.telegram_commands import TelegramCommandService


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def opportunity(direction="LONG", status="ACTIVE", symbol="SOXL"):
    return Opportunity(
        symbol=symbol, timeframe="1d", direction=direction,
        opportunity_type="PULLBACK_RESTRENGTH", strategy_name="pullback_restrength",
        strategy_version="1.0.0", status=status, score=80, confidence=90,
        detected_at=START, bar_time=START, entry_reference_price=Decimal("100"),
        stop_reference_price=Decimal("90") if direction == "LONG" else Decimal("110"),
        target_reference_price=Decimal("120") if direction == "LONG" else Decimal("80"),
        feature_snapshot_json={}, strategy_snapshot_json={}, notification_status="PENDING",
    )


def add_bars(db, symbol="SOXL", count=21):
    instrument = Instrument(
        symbol="US." + symbol, market="US", code=symbol, display_name=symbol,
        is_supported=True, support_status="SUPPORTED", support_message="测试",
    )
    db.add(instrument)
    db.flush()
    for day in range(1, count + 1):
        price = Decimal(100 + day)
        stamp = START + timedelta(days=day)
        db.add(MarketBar(
            instrument_id=instrument.id, symbol="US." + symbol, interval="1d",
            timestamp_utc=stamp, timestamp_market=stamp, trading_date=stamp.date().isoformat(),
            open=price, high=price + 2, low=price - 2, close=price,
            volume=1000, market_session="REGULAR", adjustment_type="FORWARD",
            data_source="MOOMOO", is_blank=False,
        ))
    db.commit()


def test_review_window_config():
    config = load_review_windows("config/review_windows_v1.yaml")
    assert list(config["windows"]) == ["1h", "4h", "1d", "3d", "5d", "10d", "20d"]
    assert parse_window("4h") == timedelta(hours=4)
    with pytest.raises(ValueError):
        parse_window("1w")


def test_long_metrics():
    bars = [
        {"timestamp": START, "high": "110", "low": "95", "close": "105"},
        {"timestamp": START + timedelta(hours=1), "high": "121", "low": "98", "close": "115"},
    ]
    result = calculate_metrics(Decimal("100"), bars, "LONG", Decimal("120"), Decimal("90"))
    assert result["return_percent"] == 15
    assert result["mfe_percent"] == 21
    assert result["mae_percent"] == -5
    assert result["target_hit"] and not result["stop_hit"]


def test_short_metrics():
    bars = [
        {"timestamp": START, "high": "105", "low": "90", "close": "95"},
        {"timestamp": START + timedelta(hours=1), "high": "108", "low": "79", "close": "80"},
    ]
    result = calculate_metrics(Decimal("100"), bars, "SHORT", Decimal("80"), Decimal("110"))
    assert result["return_percent"] == 20
    assert result["mfe_percent"] == 21
    assert result["mae_percent"] == -8
    assert result["target_hit"] and not result["stop_hit"]


def test_directional_return_rejects_bad_entry():
    with pytest.raises(ValueError):
        directional_return(Decimal("0"), Decimal("1"), "LONG")


def test_review_creation_price_path_and_statistics(db):
    row = opportunity()
    db.add(row)
    db.commit()
    add_bars(db)
    result = OpportunityReviewService(db).run()
    review = db.scalar(select(OpportunityReview))
    assert result["reviewed"] == 1 and review.review_status == "REVIEWED"
    assert len(review.price_path_json) == 20
    assert review.statistics_json["window_returns"]["20d"] is not None
    assert row.status == "REVIEWED"
    assert db.scalar(select(func.count()).select_from(ReviewStatistic)) >= 1


def test_review_is_idempotent(db):
    row = opportunity()
    db.add(row)
    db.commit()
    add_bars(db)
    service = OpportunityReviewService(db)
    service.run()
    service.run()
    assert db.scalar(select(func.count()).select_from(OpportunityReview)) == 1


def test_pending_when_window_not_mature(db):
    row = opportunity()
    db.add(row)
    db.commit()
    add_bars(db, count=5)
    result = OpportunityReviewService(db).run()
    assert result["pending"] == 1 and row.status == "REVIEW_PENDING"
    assert db.scalar(select(func.count()).select_from(OpportunityReview)) == 0


def test_missing_bars_becomes_review_failed(db):
    row = opportunity()
    db.add(row)
    db.commit()
    result = OpportunityReviewService(db).run()
    review = db.scalar(select(OpportunityReview))
    assert result["failed"] == 1 and row.status == "REVIEW_FAILED"
    assert review.reason_json["status"] == "DATA_INSUFFICIENT"


def test_symbol_failure_does_not_block_other(db):
    missing = opportunity(symbol="NOPE")
    valid = opportunity(symbol="SOXL")
    db.add_all([missing, valid])
    db.commit()
    add_bars(db)
    result = OpportunityReviewService(db).run()
    assert result["reviewed"] == 1 and result["failed"] == 1


def test_settings_review_defaults():
    settings = get_settings()
    assert settings.opportunity_review_enabled
    assert settings.opportunity_review_batch_size == 100


def test_telegram_review_and_admin_permission(db):
    row = opportunity()
    db.add(row)
    db.commit()
    service = TelegramCommandService(db, Settings(telegram_admin_ids="42"))
    ok, text = service.handle("42", "/review pending")
    assert ok and "待复盘Opportunity：1" in text
    assert service.handle("7", "/review")[0] is False
