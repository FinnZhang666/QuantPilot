from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.database.models import Instrument, MarketBar, TradePlan, TradeReview, UserPosition
from app.participation.service import UserParticipationService
from app.trade_lifecycle.domain import TradeDirection, TradePlanDraft
from app.trade_lifecycle.service import TradeLifecycleService
from app.trade_review.formatter import format_trade_review
from app.trade_review.metrics import calculate_excursions, classify_result
from app.trade_review.repository import TradeReviewRepository
from app.trade_review.runtime import TradeReviewRuntime
from app.trade_review.service import TradeReviewService


BASE = datetime.now(timezone.utc) - timedelta(hours=4)


def add_bars(db, direction="LONG"):
    instrument = Instrument(
        symbol="US.SOXL", market="US", code="SOXL", display_name="SOXL",
        alias="SOXL", is_supported=True,
    )
    db.add(instrument)
    db.flush()
    values = [(100, 105, 95, 102), (102, 110, 90, 108), (108, 109, 99, 105)]
    for index, (open_value, high, low, close) in enumerate(values):
        timestamp = BASE + timedelta(hours=index + 1)
        db.add(MarketBar(
            instrument_id=instrument.id, symbol="US.SOXL", interval="60m",
            timestamp_utc=timestamp, timestamp_market=timestamp,
            trading_date=timestamp.date().isoformat(), open=Decimal(open_value),
            high=Decimal(high), low=Decimal(low), close=Decimal(close), volume=100,
            market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO",
        ))
    db.commit()


def make_plan(db, direction=TradeDirection.LONG):
    lifecycle = TradeLifecycleService(db)
    plan = lifecycle.create(TradePlanDraft(
        symbol="SOXL", market="US", strategy_name="pullback_restrength",
        strategy_version="1.0.0", direction=direction, timeframe="60m",
        reference_price=Decimal("100"), stop_loss_price=Decimal("92"),
        target_prices=["108"],
    ))
    plan.created_at = BASE
    db.commit()
    return plan


def end_system_plan(db, direction=TradeDirection.LONG, stage="REVIEW"):
    lifecycle = TradeLifecycleService(db)
    plan = make_plan(db, direction)
    if stage == "REVIEW":
        lifecycle.advance(plan.plan_id, "PLAN", "确认", "TEST")
        lifecycle.advance(plan.plan_id, "COMPANION", "跟踪", "TEST")
        lifecycle.advance(plan.plan_id, "REVIEW", "结束", "TEST")
    elif stage == "CANCELLED":
        lifecycle.cancel(plan.plan_id, "取消", "TEST")
    else:
        lifecycle.expire(plan.plan_id, "过期", "TEST")
    return plan


def closed_position(db, direction=TradeDirection.LONG, exit_price="105"):
    lifecycle = TradeLifecycleService(db)
    plan = make_plan(db, direction)
    lifecycle.advance(plan.plan_id, "PLAN", "确认", "TEST")
    service = UserParticipationService(db)
    position = service.open("user-a", plan.plan_id, "100", opened_at=BASE)
    service.close(position.id, exit_price, closed_at=BASE + timedelta(hours=3))
    return plan, position


def test_long_excursions_target_and_stop():
    class Bar:
        pass
    first, second = Bar(), Bar()
    first.high, first.low = Decimal("110"), Decimal("95")
    second.high, second.low = Decimal("105"), Decimal("90")
    result = calculate_excursions("100", [first, second], "LONG", "108", "92")
    assert result == {"mfe": Decimal("10.0"), "mae": Decimal("-10.0"), "target_hit": True, "stop_hit": True}


def test_short_excursions_target_and_stop():
    class Bar:
        pass
    bar = Bar()
    bar.high, bar.low = Decimal("110"), Decimal("90")
    result = calculate_excursions("100", [bar], "SHORT", "92", "108")
    assert result["mfe"] == Decimal("10.0") and result["mae"] == Decimal("-10.0")
    assert result["target_hit"] and result["stop_hit"]


@pytest.mark.parametrize("direction,exit_price,expected", [
    ("LONG", "101", "WIN"), ("LONG", "99", "LOSS"),
    ("SHORT", "99", "WIN"), ("SHORT", "101", "LOSS"),
    ("LONG", "100", "BREAKEVEN"),
])
def test_result_classification(direction, exit_price, expected):
    assert classify_result("100", exit_price, direction) == expected


def test_system_review_requires_terminal_plan(db):
    plan = make_plan(db)
    with pytest.raises(ValueError, match="未结束"):
        TradeReviewRuntime(db).generate_review("SYSTEM", plan.id, dry_run=True)


def test_user_review_requires_closed_position(db):
    lifecycle = TradeLifecycleService(db)
    plan = make_plan(db)
    lifecycle.advance(plan.plan_id, "PLAN", "确认", "TEST")
    position = UserParticipationService(db).open("user-a", plan.plan_id, "100", opened_at=BASE)
    with pytest.raises(ValueError, match="CLOSED"):
        TradeReviewRuntime(db).generate_review("USER", position.id, dry_run=True)


def test_system_review_creation_and_idempotent_update(db):
    add_bars(db)
    plan = end_system_plan(db)
    runtime = TradeReviewRuntime(db)
    first, created = runtime.generate_review("SYSTEM", plan.id, dry_run=False)
    second, created_again = runtime.generate_review("SYSTEM", plan.id, dry_run=False)
    assert created and not created_again and first.id == second.id
    assert first.result == "WIN" and first.mfe == Decimal("10.00000000")
    assert first.mae == Decimal("-10.00000000") and first.target_hit and first.stop_hit
    assert db.scalar(select(func.count()).select_from(TradeReview)) == 1


@pytest.mark.parametrize("stage,expected", [("CANCELLED", "CANCELLED"), ("EXPIRED", "EXPIRED")])
def test_terminal_plan_result_is_preserved(db, stage, expected):
    add_bars(db)
    plan = end_system_plan(db, stage=stage)
    row, _ = TradeReviewRuntime(db).generate_review("SYSTEM", plan.id, dry_run=False)
    assert row.result == expected


def test_user_review_holding_and_plan_immutability(db):
    add_bars(db)
    plan, position = closed_position(db)
    before = (plan.lifecycle_stage, position.status, position.exit_price)
    review, _ = TradeReviewRuntime(db).generate_review("USER", position.id, dry_run=False)
    db.refresh(plan)
    db.refresh(position)
    assert review.result == "WIN" and review.holding_minutes == 180
    assert (plan.lifecycle_stage, position.status, position.exit_price) == before


def test_dry_run_does_not_write(db):
    add_bars(db)
    plan = end_system_plan(db)
    result = TradeReviewRuntime(db).generate_reviews(dry_run=True)
    assert result["created"] == 1 and result["scanned"] == 1
    assert db.scalar(select(func.count()).select_from(TradeReview)) == 0


def test_backfill_filters_and_repeat_update(db):
    add_bars(db)
    end_system_plan(db)
    runtime = TradeReviewRuntime(db)
    ignored = runtime.generate_reviews(dry_run=False, symbol="QQQ")
    first = runtime.generate_reviews(dry_run=False, symbol="SOXL", strategy="pullback_restrength")
    second = runtime.generate_reviews(dry_run=False, symbol="SOXL")
    assert ignored["scanned"] == 0 and first["created"] == 1
    assert second["updated"] == 1 and db.scalar(select(func.count()).select_from(TradeReview)) == 1


def test_backfill_date_range_uses_terminal_time(db):
    add_bars(db)
    end_system_plan(db)
    runtime = TradeReviewRuntime(db)
    recent = runtime.generate_reviews(
        dry_run=True, start_time=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    old = runtime.generate_reviews(dry_run=True, end_time=BASE + timedelta(minutes=1))
    assert recent["scanned"] == 1 and old["scanned"] == 0


def test_missing_bars_isolated_as_failure(db):
    end_system_plan(db)
    result = TradeReviewRuntime(db).generate_reviews(dry_run=False)
    assert result["status"] == "PARTIAL_SUCCESS" and result["failed"] == 1
    assert result["errors"][0]["error"] == "ValueError"


def test_statistics_repository_and_formatter(db):
    add_bars(db)
    plan = end_system_plan(db)
    review, _ = TradeReviewRuntime(db).generate_review("SYSTEM", plan.id, dry_run=False)
    repository = TradeReviewRepository(db)
    assert repository.get(review.id).review_key == "SYSTEM:%s" % plan.id
    assert repository.count(review_type="SYSTEM", symbol="SOXL") == 1
    stats = TradeReviewService(db).statistics()
    assert stats["system"]["total_reviews"] == 1 and stats["system"]["wins"] == 1
    text = format_trade_review(review, "SOXL")
    assert "MFE:" in text and "不构成交易建议" in text
