from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.capital_management.backtest import compare_profit_lock
from app.capital_management.service import CapitalManagementService
from app.core.config import Settings
from app.database.models import (
    CapitalManagementState, CapitalTransfer, Instrument, MarketBar,
    SystemPaperAccount, SystemPaperAuditEvent,
)
from app.runtime.paper_notifications import PaperEventNotificationDispatcher
from app.paper_runtime.service import PaperTradingService


NOW = datetime(2026, 8, 25, 20, tzinfo=timezone.utc)


def config(**changes):
    values = {"profit_lock_enabled": True, "paper_trading_initial_cash": 100000,
              "profit_lock_trigger": .10, "profit_lock_ratio": .30,
              "profit_lock_reserve_allocation": .70, "profit_lock_core_allocation": .30,
              "profit_lock_core_symbol": "SPY", "profit_lock_reserve_mode": "CASH"}
    values.update(changes)
    return Settings(_env_file=None, **values)


def account(db, realized="0", cash="100000"):
    row = SystemPaperAccount(account_key="system-paper", base_currency="USD",
        initial_cash=Decimal("100000"), available_cash=Decimal(cash), reserved_cash=0,
        position_market_value=0, total_equity=Decimal(cash), realized_pnl=Decimal(realized),
        unrealized_pnl=0, peak_equity=Decimal("100000"), max_drawdown=0)
    db.add(row); db.commit()
    return row


def spy_bar(db, price="500"):
    instrument = Instrument(symbol="US.SPY", market="US", code="SPY", display_name="SPY")
    db.add(instrument); db.flush()
    db.add(MarketBar(instrument_id=instrument.id, symbol="US.SPY", interval="1d",
        timestamp_utc=NOW, timestamp_market=NOW, trading_date=NOW.date(),
        open=price, high=price, low=price, close=price, volume=100,
        market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO"))
    db.commit()


def test_profit_trigger_allocates_three_buckets(db):
    row = account(db, "10000", "110000"); spy_bar(db)
    result = CapitalManagementService(db, config()).process(row, NOW); db.commit()
    state = db.scalar(select(CapitalManagementState))
    assert result["allocated"] == "3000.00000000"
    assert row.available_cash == Decimal("107000")
    assert state.reserve_principal == Decimal("2100")
    assert state.core_principal == Decimal("900") and state.core_units == Decimal("1.8")
    assert db.scalar(select(func.count()).select_from(CapitalTransfer)) == 2


def test_high_water_mark_prevents_duplicate_lock(db):
    row = account(db, "10000", "110000")
    service = CapitalManagementService(db, config())
    assert service.process(row, NOW)["triggered"] is True
    row.realized_pnl = Decimal("5000")
    assert service.process(row, NOW + timedelta(days=1))["triggered"] is False
    row.realized_pnl = Decimal("10000")
    assert service.process(row, NOW + timedelta(days=2))["triggered"] is False
    assert db.scalar(select(func.count()).select_from(CapitalTransfer)) == 2


def test_next_profit_step_locks_only_new_profit_step(db):
    row = account(db, "10000", "120000")
    service = CapitalManagementService(db, config())
    service.process(row, NOW)
    row.realized_pnl = Decimal("20000")
    result = service.process(row, NOW + timedelta(days=1))
    assert result["allocated"] == "3000.00000000"
    assert service.state(row).total_locked_transfer == Decimal("6000")


def test_reserve_never_returns_to_active_after_drawdown(db):
    row = account(db, "10000", "110000")
    service = CapitalManagementService(db, config()); service.process(row, NOW)
    reserve = service.state(row).reserve_principal
    row.realized_pnl = Decimal("-20000"); row.available_cash = Decimal("87000")
    service.process(row, NOW + timedelta(days=1))
    assert service.state(row).reserve_principal == reserve
    assert row.available_cash == Decimal("87000")


def test_missing_spy_price_stays_explicit_pending_cash(db):
    row = account(db, "10000", "110000")
    service = CapitalManagementService(db, config()); service.process(row, NOW)
    summary = service.summary(row)
    assert Decimal(summary["core_pending_cash"]) == Decimal("900")
    assert Decimal(summary["core_units"]) == 0
    assert Decimal(summary["core_value"]) == Decimal("900")


def test_core_market_loss_does_not_change_locked_reserve(db):
    row = account(db, "10000", "110000"); spy_bar(db, "500")
    service = CapitalManagementService(db, config()); service.process(row, NOW)
    state = service.state(row); reserve = state.reserve_value
    db.add(MarketBar(instrument_id=db.scalar(select(Instrument.id)), symbol="US.SPY", interval="1d",
        timestamp_utc=NOW + timedelta(days=1), timestamp_market=NOW + timedelta(days=1),
        trading_date=(NOW + timedelta(days=1)).date(), open=400, high=400, low=400, close=400,
        volume=100, market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO")); db.flush()
    summary = service.summary(row)
    assert Decimal(summary["core_value"]) == Decimal("720")
    assert state.reserve_value == reserve == Decimal("2100")


def test_active_buying_power_isolated_from_reserve(db):
    row = account(db, "10000", "110000")
    service = CapitalManagementService(db, config()); service.process(row, NOW)
    summary = service.summary(row)
    assert Decimal(summary["active_available_cash"]) == Decimal("107000")
    assert Decimal(summary["active_available_cash"]) + Decimal(summary["reserve_value"]) != Decimal("107000")

    sizing = config(paper_trading_sizing_mode="FIXED_CASH",
        paper_trading_fixed_cash_per_trade=108000, paper_trading_min_cash_reserve_pct=0,
        paper_trading_allow_fractional=False, paper_trading_max_symbol_exposure_pct=1,
        paper_trading_max_strategy_exposure_pct=1, paper_trading_max_gross_exposure_pct=2)
    plan = SimpleNamespace(symbol="QQQ", direction="LONG", strategy_name="pullback_restrength")
    quantity, error = PaperTradingService(db, sizing)._position_quantity(row, plan, Decimal("100"))
    assert error is None and quantity == Decimal("1070")


def test_insufficient_active_cash_does_not_create_partial_transfer(db):
    row = account(db, "10000", "1000")
    result = CapitalManagementService(db, config()).process(row, NOW)
    assert result["error"] == "INSUFFICIENT_ACTIVE_CASH"
    assert db.scalar(select(func.count()).select_from(CapitalTransfer)) == 0
    assert row.available_cash == Decimal("1000")


def test_initial_capital_recovery_uses_reserve_only(db):
    row = account(db, "100000", "200000")
    service = CapitalManagementService(db, config(
        profit_lock_ratio=1, profit_lock_reserve_allocation=1, profit_lock_core_allocation=0))
    service.process(row, NOW)
    summary = service.summary(row)
    assert summary["initial_capital_recovered"] is True
    assert Decimal(summary["capital_recovered_ratio"]) == 1


def test_capital_backtest_keeps_strategy_profit_separate():
    scenarios = [
        {"name": "none", "trigger_ratio": .1, "lock_ratio": 0, "reserve_ratio": 1},
        {"name": "30pct", "trigger_ratio": .1, "lock_ratio": .3, "reserve_ratio": .7},
    ]
    values = compare_profit_lock(100000, [0, 10000, 20000], scenarios)
    assert values[0]["strategy_profit"] == values[1]["strategy_profit"] == "20000"
    assert Decimal(values[1]["locked_profit"]) == Decimal("4200.00")
    assert Decimal(values[1]["core_value"]) == Decimal("1800.00")


def test_profit_lock_telegram_copy_is_low_frequency_event():
    event = type("Event", (), {"event_type": "PROFIT_LOCK_ALLOCATED", "details_json": {
        "locked_amount": "3000", "reserve_amount": "2100", "core_amount": "900",
        "active_trading_cash": "107000"}})()
    text = PaperEventNotificationDispatcher._render(event, None, "zh-CN")
    assert "利润锁定完成" in text and "2100" in text and "SPY" in text


def test_invalid_allocation_config_fails_early():
    with pytest.raises(ValueError, match="之和必须为1"):
        config(profit_lock_reserve_allocation=.8, profit_lock_core_allocation=.3)
