from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
import pytest

from app.core.config import Settings
from app.database.models import (
    Instrument, MarketBar, SystemEquitySnapshot, SystemPaperOrder,
    SystemPaperPosition, TradePlan, TradeReview,
)
from app.paper_runtime.manager import RuntimeManager
from app.paper_runtime.service import PaperTradingService
from app.trade_review.runtime import TradeReviewRuntime


NOW = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)


def settings(**changes):
    values = {
        "paper_trading_enabled": True, "runtime_manager_enabled": True,
        "review_runtime_enabled": True, "strategy_scoreboard_enabled": True,
        "paper_trading_initial_cash": 100000, "paper_trading_slippage_bps": 0,
        "paper_trading_fee_per_order": 0, "paper_trading_position_pct": 0.1,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def add_bar(db, timestamp, low="99", high="101", close="100"):
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == "US.QQQ"))
    if instrument is None:
        instrument = Instrument(
            symbol="US.QQQ", market="US", code="QQQ", display_name="QQQ",
            is_supported=True,
        )
        db.add(instrument); db.flush()
    db.add(MarketBar(
        instrument_id=instrument.id, symbol="US.QQQ", interval="1d",
        timestamp_utc=timestamp, timestamp_market=timestamp,
        trading_date=timestamp.date(), open=close, high=high, low=low, close=close,
        volume=100, market_session="REGULAR", adjustment_type="FORWARD",
        data_source="MOOMOO",
    ))
    db.commit()


def add_plan(db, **changes):
    values = dict(
        plan_id="paper-plan", symbol="QQQ", market="US",
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        lifecycle_stage="PLAN", direction="LONG", timeframe="1d",
        reference_price=Decimal("100"), stop_loss_price=Decimal("95"),
        target_prices_json=["110"], plan_status="ACTIVE",
        created_at=NOW - timedelta(minutes=5),
    )
    values.update(changes)
    row = TradePlan(**values)
    db.add(row); db.commit(); return row


def test_safe_disabled_does_not_create_account(db):
    result = PaperTradingService(db, settings(paper_trading_enabled=False)).process_once()
    assert result["status"] == "DISABLED"
    assert db.scalar(select(func.count()).select_from(SystemPaperOrder)) == 0


def test_entry_is_trade_plan_driven_filled_and_idempotent(db):
    add_bar(db, NOW)
    plan = add_plan(db)
    service = PaperTradingService(db, settings())
    first = service.process_once()
    second = service.process_once()
    position = db.scalar(select(SystemPaperPosition))
    assert first["opened"] == 1 and second["opened"] == 0
    assert db.scalar(select(func.count()).select_from(SystemPaperOrder)) == 1
    assert db.scalar(select(func.count()).select_from(SystemEquitySnapshot)) == 1
    assert position.trade_plan_id == plan.id and position.quantity == Decimal("100")
    assert plan.lifecycle_stage == "COMPANION"


def test_missing_entry_and_short_do_not_open(db):
    add_bar(db, NOW)
    add_plan(db, plan_id="missing", reference_price=None, stop_loss_price=None,
             target_prices_json=[])
    add_plan(db, plan_id="short", direction="SHORT")
    result = PaperTradingService(db, settings()).process_once()
    statuses = set(db.scalars(select(SystemPaperOrder.status)))
    assert result["opened"] == 0
    assert statuses == {"WAITING_ENTRY_DATA", "WAITING_UNSUPPORTED_DIRECTION"}


def test_waiting_order_retries_on_new_bar_without_duplicate(db):
    add_bar(db, NOW, low="110", high="120", close="115")
    add_plan(db)
    service = PaperTradingService(db, settings())
    assert service.process_once()["waiting"] == 1
    add_bar(db, NOW + timedelta(days=1), low="99", high="101", close="100")
    assert service.process_once()["opened"] == 1
    assert db.scalar(select(func.count()).select_from(SystemPaperOrder)) == 1


def test_stop_has_priority_closes_values_and_generates_review(db):
    add_bar(db, NOW)
    plan = add_plan(db)
    service = PaperTradingService(db, settings())
    service.process_once()
    add_bar(db, NOW + timedelta(days=1), low="94", high="111", close="105")
    result = service.process_once()
    position = db.scalar(select(SystemPaperPosition))
    assert result["closed"] == 1
    assert position.exit_reason == "STOP_LOSS" and position.exit_price == Decimal("95")
    assert plan.lifecycle_stage == "REVIEW"
    assert db.scalar(select(func.count()).select_from(SystemEquitySnapshot)) >= 2
    review_result = TradeReviewRuntime(db).generate_reviews(dry_run=False)
    assert review_result["created"] == 1
    assert db.scalar(select(func.count()).select_from(TradeReview)) == 1


def test_runtime_manager_process_once_and_disabled_snapshot(db):
    factory = lambda: db
    disabled = RuntimeManager(settings(runtime_manager_enabled=False), factory)
    assert disabled.process_once()["disabled"] is True
    manager = RuntimeManager(settings(paper_trading_enabled=False), factory)
    result = manager.process_once()
    assert result["paper"]["status"] == "DISABLED"


def test_review_failure_does_not_rollback_closed_position(db):
    add_bar(db, NOW)
    add_plan(db)
    service = PaperTradingService(db, settings())
    service.process_once()
    add_bar(db, NOW + timedelta(days=1), low="94", high="96", close="95")
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    manager = RuntimeManager(settings(), factory)
    manager.review.process_once = lambda: (_ for _ in ()).throw(RuntimeError("review failed"))
    with pytest.raises(RuntimeError, match="review failed"):
        manager.process_once()
    db.expire_all()
    position = db.scalar(select(SystemPaperPosition))
    assert position.status == "CLOSED" and position.exit_reason == "STOP_LOSS"
