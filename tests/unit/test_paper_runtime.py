from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.database.models import (
    CandidateSignal,
    Instrument,
    MarketBar,
    SystemEquitySnapshot,
    SystemPaperAuditEvent,
    SystemPaperFill,
    SystemPaperOrder,
    SystemPaperPosition,
    TradePlan,
    TradeReview,
)
from app.paper_runtime.manager import RuntimeManager
from app.paper_runtime.performance import PaperPerformanceService
from app.paper_runtime.review import SystemPaperReviewService
from app.paper_runtime.scheduler import PaperScheduler
from app.paper_runtime.service import PaperTradingService


NOW = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)


def settings(**changes):
    values = {
        "paper_trading_enabled": True, "runtime_manager_enabled": True,
        "paper_scheduler_enabled": False, "review_runtime_enabled": True,
        "strategy_scoreboard_enabled": True, "paper_trading_initial_cash": 100000,
        "paper_trading_slippage_bps": 0, "paper_trading_fee_per_order": 0,
        "paper_trading_position_pct": 0.1, "paper_trading_min_cash_reserve_pct": 0,
        "paper_trading_max_symbol_exposure_pct": 1,
        "paper_trading_max_strategy_exposure_pct": 1,
        "paper_trading_max_gross_exposure_pct": 1,
        "paper_trading_sqlite_lock_backoff_seconds": 0,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def add_bar(db, timestamp, low="99", high="101", close="100", open_price=None, symbol="QQQ"):
    full = "US." + symbol
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == full))
    if instrument is None:
        instrument = Instrument(
            symbol=full, market="US", code=symbol, display_name=symbol,
            is_supported=True,
        )
        db.add(instrument)
        db.flush()
    db.add(MarketBar(
        instrument_id=instrument.id, symbol=full, interval="1d",
        timestamp_utc=timestamp, timestamp_market=timestamp,
        trading_date=timestamp.date(), open=open_price or close,
        high=high, low=low, close=close, volume=100,
        market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO",
    ))
    db.commit()


def add_plan(db, key="plan", direction="LONG", **changes):
    candidate = CandidateSignal(
        symbol="QQQ", market="US", timeframe="1d",
        bar_timestamp=NOW - timedelta(minutes=10),
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        parameters_hash=(key + "0" * 64)[:64], signal_type="CANDIDATE_BUY",
        score=80, confidence=80, status="VALID", summary_zh="test",
        reasons_json=[], risks_json=[], feature_refs_json={}, components_json={},
    )
    db.add(candidate)
    db.flush()
    values = dict(
        plan_id=key, signal_id=candidate.id, symbol="QQQ", market="US",
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        lifecycle_stage="PLAN", direction=direction, timeframe="1d",
        reference_price=Decimal("100"), stop_loss_price=Decimal("95") if direction == "LONG" else Decimal("105"),
        target_prices_json=["110"] if direction == "LONG" else ["90"],
        plan_status="ACTIVE", created_at=NOW - timedelta(minutes=5),
    )
    values.update(changes)
    row = TradePlan(**values)
    db.add(row)
    db.commit()
    return row


def open_position(db, direction="LONG", **setting_changes):
    add_bar(db, NOW)
    plan = add_plan(db, key="open-" + direction.lower(), direction=direction)
    service = PaperTradingService(db, settings(**setting_changes))
    result = service.process_once()
    return service, plan, db.scalar(select(SystemPaperPosition)), result


def test_disabled_and_dry_run_are_read_only(db):
    add_bar(db, NOW)
    add_plan(db)
    disabled = PaperTradingService(db, settings(paper_trading_enabled=False))
    assert disabled.process_once()["status"] == "DISABLED"
    before = db.scalar(select(func.count()).select_from(SystemPaperOrder))
    report = disabled.dry_run(max_entries=1)
    assert report["status"] == "DRY_RUN" and report["expected_orders"] == 1
    assert db.scalar(select(func.count()).select_from(SystemPaperOrder)) == before == 0


def test_trade_plan_trigger_entry_and_idempotency(db):
    service, plan, position, first = open_position(db)
    second = service.process_once()
    assert first["opened"] == 1 and second["opened"] == 0
    assert db.scalar(select(func.count()).select_from(SystemPaperOrder)) == 1
    assert position.trade_plan_id == plan.id and position.quantity == Decimal("100")
    assert plan.lifecycle_stage == "COMPANION"


def test_entry_not_triggered_then_new_bar_fills_without_future_data(db):
    add_bar(db, NOW, low="110", high="120", close="115")
    add_plan(db)
    service = PaperTradingService(db, settings())
    assert service.process_once()["waiting"] == 1
    add_bar(db, NOW + timedelta(days=1), low="99", high="101", close="100")
    assert service.process_once()["opened"] == 1
    order = db.scalar(select(SystemPaperOrder))
    assert order.metadata_json["last_evaluated_bar"].startswith("2026-08-01")


def test_missing_candidate_and_missing_entry_are_explicit(db):
    add_bar(db, NOW)
    missing_candidate = TradePlan(
        plan_id="missing-candidate", symbol="QQQ", market="US",
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        lifecycle_stage="PLAN", direction="LONG", timeframe="1d",
        reference_price=Decimal("100"), plan_status="ACTIVE",
        created_at=NOW - timedelta(minutes=5),
    )
    db.add(missing_candidate)
    missing_entry = add_plan(db, key="missing-entry", reference_price=None)
    result = PaperTradingService(db, settings()).process_once()
    statuses = {row.trade_plan_id: (row.status, row.rejection_code) for row in db.scalars(select(SystemPaperOrder))}
    assert result["opened"] == 0
    assert statuses[missing_candidate.id] == ("REJECTED", "MISSING_CANDIDATE")
    assert statuses[missing_entry.id] == ("WAITING_ENTRY_DATA", "MISSING_ENTRY_PRICE")


def test_insufficient_cash_and_position_limits_reject(db):
    add_bar(db, NOW)
    add_plan(db)
    result = PaperTradingService(db, settings(
        paper_trading_initial_cash=50,
        paper_trading_sizing_mode="FIXED_CASH",
        paper_trading_fixed_cash_per_trade=10000,
        paper_trading_min_cash_reserve_pct=0.9,
        paper_trading_max_gross_exposure_pct=2,
    )).process_once()
    order = db.scalar(select(SystemPaperOrder))
    assert result["rejected"] == 1
    assert order.status == "REJECTED"
    assert order.rejection_code in {"INSUFFICIENT_PAPER_CASH", "MINIMUM_CASH_RESERVE"}


def test_long_stop_is_conservative_on_gap(db):
    service, _, position, _ = open_position(db)
    add_bar(db, NOW + timedelta(days=1), low="89", high="101", close="92", open_price="90")
    result = service.process_once()
    assert result["closed"] == 1
    assert position.status == "CLOSED" and position.exit_reason == "STOP_LOSS"
    assert position.exit_price == Decimal("90")


def test_long_target(db):
    service, _, position, _ = open_position(db)
    add_bar(db, NOW + timedelta(days=1), low="99", high="111", close="109")
    service.process_once()
    assert position.status == "CLOSED" and position.exit_reason == "TARGET_1"
    assert position.realized_pnl == Decimal("1000")


def test_short_stop_and_target_are_mirrored(db):
    service, _, position, _ = open_position(db, direction="SHORT")
    assert position.direction == "SHORT" and position.market_value == Decimal("-10000")
    add_bar(db, NOW + timedelta(days=1), low="99", high="108", close="106", open_price="107")
    service.process_once()
    assert position.status == "CLOSED" and position.exit_price == Decimal("107")
    assert position.realized_pnl == Decimal("-700")

    db.query(SystemPaperPosition).delete(); db.query(SystemPaperFill).delete(); db.query(SystemPaperOrder).delete()
    db.query(TradePlan).delete(); db.query(CandidateSignal).delete(); db.commit()
    db.query(MarketBar).delete(); db.commit(); add_bar(db, NOW)
    add_plan(db, key="short-target", direction="SHORT")
    service = PaperTradingService(db, settings())
    assert service.process_once()["opened"] == 1
    target_position = db.scalar(select(SystemPaperPosition))
    add_bar(db, NOW + timedelta(days=2), low="89", high="101", close="91")
    service.process_once()
    assert target_position.exit_reason == "TARGET_1" and target_position.realized_pnl == Decimal("990")


def test_same_bar_stop_target_uses_ambiguous_stop_priority(db):
    service, _, position, _ = open_position(db)
    add_bar(db, NOW + timedelta(days=1), low="94", high="111", close="105")
    service.process_once()
    assert position.exit_reason == "AMBIGUOUS_STOP_PRIORITY"
    assert position.exit_price == Decimal("95")


def test_partial_reduce_then_full_exit(db):
    add_bar(db, NOW)
    add_plan(db, target_prices_json=["105", "110"])
    service = PaperTradingService(db, settings())
    service.process_once()
    position = db.scalar(select(SystemPaperPosition))
    add_bar(db, NOW + timedelta(days=1), low="99", high="106", close="104")
    first = service.process_once()
    assert first["partial"] == 1 and position.status == "OPEN"
    assert position.quantity == Decimal("50") and position.target_index == 1
    add_bar(db, NOW + timedelta(days=2), low="103", high="111", close="109")
    service.process_once()
    assert position.status == "CLOSED" and position.realized_pnl == Decimal("750")
    assert db.scalar(select(func.count()).select_from(SystemPaperOrder)) == 3


def test_cancelled_plan_and_max_holding_exit(db):
    service, plan, position, _ = open_position(db)
    plan.lifecycle_stage = "CANCELLED"; db.commit()
    add_bar(db, NOW + timedelta(days=1), low="98", high="102", close="101")
    service.process_once()
    assert position.exit_reason == "CANCELLED"

    db.query(SystemPaperPosition).delete(); db.query(SystemPaperFill).delete(); db.query(SystemPaperOrder).delete()
    db.query(TradePlan).delete(); db.query(CandidateSignal).delete(); db.commit()
    add_plan(db, key="max-hold")
    service = PaperTradingService(db, settings(paper_trading_max_holding_bars=1))
    service.process_once()
    held = db.scalar(select(SystemPaperPosition))
    add_bar(db, NOW + timedelta(days=2), low="99", high="101", close="100")
    service.process_once()
    assert held.exit_reason == "MAX_HOLDING_PERIOD"


def test_manual_close_and_safety_close(db):
    service, _, position, _ = open_position(db)
    add_bar(db, NOW + timedelta(days=1), low="100", high="103", close="102")
    service.manual_close(position.id, "MANUAL_CLOSE", Decimal("50"))
    assert position.status == "OPEN" and position.quantity == Decimal("50")
    service.manual_close(position.id, "SAFETY_CLOSE")
    assert position.status == "CLOSED" and position.exit_reason == "SAFETY_CLOSE"


def test_valuation_daily_return_drawdown_and_stale_data(db):
    service, _, position, _ = open_position(db, paper_trading_stale_daily_seconds=86400)
    account = service.account()
    service.value_account(account, source="STALE_TEST", valuation_time=NOW + timedelta(days=2))
    assert position.market_data_status == "STALE"
    add_bar(db, NOW + timedelta(days=1), low="89", high="101", close="90")
    service.value_account(account, source="TEST_REVALUE")
    db.commit()
    assert account.total_equity == Decimal("99000")
    assert account.total_return == Decimal("-0.01")
    assert account.max_drawdown == Decimal("-0.01")
    snapshot = db.scalar(select(SystemEquitySnapshot).order_by(desc(SystemEquitySnapshot.id)))
    assert snapshot.drawdown == Decimal("-0.01")


def test_auto_review_exact_snapshot_and_idempotency(db):
    service, _, position, _ = open_position(db)
    add_bar(db, NOW + timedelta(days=1), low="99", high="111", close="109")
    service.process_once()
    review_service = SystemPaperReviewService(db)
    first = review_service.generate_pending()
    second = review_service.generate_pending()
    review = db.scalar(select(TradeReview))
    assert first["created"] == 1 and second["created"] == 0
    assert review.system_paper_position_id == position.id
    assert review.review_key.startswith("SYSTEM_PAPER:")
    assert review.source_snapshot_json["exit_reason"] == "TARGET_1"


def test_scoreboard_complete_statistics(db):
    service, _, _, _ = open_position(db)
    add_bar(db, NOW + timedelta(days=1), low="99", high="111", close="109")
    service.process_once()
    item = PaperPerformanceService(db).scoreboard()[0]
    assert item["trade_count"] == 1 and item["closed_trades"] == 1
    assert item["wins"] == 1 and item["win_rate"] == Decimal("1")
    assert item["average_return"] == Decimal("0.1")
    assert item["sample_size"] == 1 and item["sharpe"] is None


def test_audit_chain_is_complete_and_sanitized(db):
    service, plan, position, _ = open_position(db)
    add_bar(db, NOW + timedelta(days=1), low="99", high="111", close="109")
    service.process_once(); SystemPaperReviewService(db).generate_pending()
    events = list(db.scalars(select(SystemPaperAuditEvent)))
    types = {row.event_type for row in events}
    assert {"CANDIDATE_EVALUATED", "TRADE_PLAN_EVALUATED", "ORDER_CREATED",
            "FILL_CREATED", "POSITION_OPENED", "POSITION_CLOSED",
            "EQUITY_UPDATED", "REVIEW_GENERATED"}.issubset(types)
    trace = [row for row in events if row.position_id == position.id]
    assert trace and all(row.trade_plan_id in {None, plan.id} for row in trace)
    assert all("token" not in str(row.details_json).lower() for row in events)


def test_runtime_lock_restart_recovery(db):
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    first = RuntimeManager(settings(), factory)
    second = RuntimeManager(settings(), factory)
    assert first.start()["status"] == "RUNNING"
    blocked = second.start()
    assert blocked["status"] == "FAILED" and blocked["lock_conflict"] is True
    first.stop()
    assert second.start()["status"] == "RUNNING"
    assert second.stop()["status"] == "STOPPED"


def test_scheduler_non_overlap_and_sqlite_lock_retry(db):
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    scheduler = PaperScheduler(settings(), factory)
    scheduler._run_lock.acquire()
    try:
        assert scheduler.run_once()["status"] == "BUSY"
    finally:
        scheduler._run_lock.release()
    attempts = {"count": 0}

    def callback():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise OperationalError("database is locked", {}, None)
        return {"status": "SUCCESS"}

    assert scheduler._with_sqlite_retry(callback)["status"] == "SUCCESS"
    assert attempts["count"] == 3


def test_real_order_transport_safety_scan():
    root = Path(__file__).resolve().parents[2] / "app" / "paper_runtime"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in root.glob("*.py")
    ).lower()
    assert "place_order(" not in source
    assert "trdcontext" not in source
    assert "import telegram" not in source
    assert "from app.telegram" not in source
    assert ".send_message(" not in source
    assert "google.generativeai" not in source
    assert "broker_account_id" not in source
