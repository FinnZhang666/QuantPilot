from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Optional

from sqlalchemy import desc, select

from app.database.models import (
    CapitalManagementState, CapitalTransfer, MarketBar, SystemPaperAccount,
)
from app.paper_runtime.audit import PaperAudit


D = Decimal
MONEY = D("0.00000001")


class CapitalManagementService:
    """Moves realized profit out of active capital without changing strategy P/L."""

    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.audit = PaperAudit(db)

    def state(self, account: SystemPaperAccount, create=True) -> Optional[CapitalManagementState]:
        row = self.db.scalar(select(CapitalManagementState).where(
            CapitalManagementState.account_id == account.id,
        ))
        if row is None and create:
            initial = D(str(account.initial_cash))
            row = CapitalManagementState(
                account_id=account.id, initial_capital=initial,
                core_symbol=self.settings.profit_lock_core_symbol.upper(),
                reserve_mode=self.settings.profit_lock_reserve_mode,
                capital_management_version=self.settings.capital_management_version,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def process(self, account: SystemPaperAccount, at=None):
        """Allocate every newly crossed profit step exactly once, transactionally."""
        at = at or datetime.now(timezone.utc)
        if not self.settings.profit_lock_enabled:
            row = self.state(account)
            row.status = "PAUSED"
            return {"status": "PAUSED", "triggered": False, "allocated": "0"}
        with self.db.begin_nested():
            row = self.state(account)
            realized = max(D("0"), D(str(account.realized_pnl)))
            step = D(str(row.initial_capital)) * D(str(self.settings.profit_lock_trigger))
            if step <= 0:
                raise ValueError("Profit Lock trigger step must be positive")
            crossed = int((realized / step).to_integral_value(rounding=ROUND_FLOOR))
            completed = int((D(str(row.profit_lock_high_water_mark)) / step).to_integral_value(
                rounding=ROUND_FLOOR))
            new_steps = max(0, crossed - completed)
            if not new_steps:
                if row.status != "ALLOCATED":
                    row.status = "ACCUMULATING"
                self.refresh_values(row)
                return {"status": row.status, "triggered": False, "allocated": "0",
                        "next_trigger_profit": str((completed + 1) * step)}
            lock_amount = (step * new_steps * D(str(self.settings.profit_lock_ratio))).quantize(MONEY)
            if D(str(account.available_cash)) < lock_amount:
                row.status = "TRIGGERED"
                return {"status": "TRIGGERED", "triggered": True, "allocated": "0",
                        "error": "INSUFFICIENT_ACTIVE_CASH"}
            reserve = (lock_amount * D(str(self.settings.profit_lock_reserve_allocation))).quantize(MONEY)
            core = lock_amount - reserve
            new_hwm = step * crossed
            account.available_cash = D(str(account.available_cash)) - lock_amount
            account.total_equity = D(str(account.total_equity)) - lock_amount
            row.status = "TRIGGERED"
            if reserve:
                row.reserve_principal = D(str(row.reserve_principal)) + reserve
                row.reserve_value = D(str(row.reserve_value)) + reserve
                self._transfer(account, row, "RESERVE", reserve, realized, new_hwm, "PROFIT_LOCK", at)
            if core:
                row.core_principal = D(str(row.core_principal)) + core
                self._allocate_core(row, core, at)
                self._transfer(account, row, "LONG_TERM_CORE", core, realized, new_hwm,
                               "PROFIT_REALLOCATION", at)
            row.total_locked_transfer = D(str(row.total_locked_transfer)) + lock_amount
            row.profit_lock_high_water_mark = new_hwm
            row.last_trigger_at = at
            row.status = "ALLOCATED"
            if row.initial_capital_recovered_at is None and D(str(row.reserve_principal)) >= D(str(row.initial_capital)):
                row.initial_capital_recovered_at = at
                self.audit.record("INITIAL_CAPITAL_RECOVERED", details={
                    "reserve_principal": str(row.reserve_principal), "initial_capital": str(row.initial_capital),
                    "capital_management_version": row.capital_management_version,
                })
            self.refresh_values(row)
            self.audit.record("PROFIT_LOCK_ALLOCATED", details={
                "locked_amount": str(lock_amount), "reserve_amount": str(reserve),
                "core_amount": str(core), "active_trading_cash": str(account.available_cash),
                "trigger_profit": str(realized), "high_water_mark": str(new_hwm),
                "capital_management_version": row.capital_management_version,
            })
            return {"status": row.status, "triggered": True, "allocated": str(lock_amount),
                    "reserve": str(reserve), "core": str(core), "high_water_mark": str(new_hwm)}

    def refresh_values(self, row: CapitalManagementState, at=None):
        price = self._core_price(row.core_symbol, at)
        if price is not None:
            row.core_last_price = price
        market = D(str(row.core_units)) * D(str(row.core_last_price or 0))
        row.core_value = market + D(str(row.core_pending_cash))
        row.reserve_value = D(str(row.reserve_principal)) + D(str(row.reserve_yield))
        return row

    def summary(self, account: SystemPaperAccount, create=False):
        row = self.state(account, create=create)
        initial = D(str(account.initial_cash))
        if row is None:
            return self._empty_summary(account, initial)
        self.refresh_values(row)
        active = D(str(account.total_equity))
        reserve = D(str(row.reserve_value))
        core = D(str(row.core_value))
        total = active + reserve + core
        realized = D(str(account.realized_pnl))
        return {
            "status": row.status, "capital_management_version": row.capital_management_version,
            "initial_capital": str(initial), "active_trading_equity": str(active),
            "active_available_cash": str(account.available_cash),
            "realized_strategy_profit": str(realized),
            "unrealized_strategy_profit": str(account.unrealized_pnl),
            "total_locked_transfer": str(row.total_locked_transfer),
            "reserve_principal": str(row.reserve_principal), "reserve_value": str(reserve),
            "reserve_yield": str(row.reserve_yield), "reserve_mode": row.reserve_mode,
            "core_symbol": row.core_symbol, "core_principal": str(row.core_principal),
            "core_value": str(core), "core_pnl": str(core - D(str(row.core_principal))),
            "core_units": str(row.core_units), "core_pending_cash": str(row.core_pending_cash),
            "total_wealth": str(total),
            "capital_recovered_ratio": str(self._ratio(row.reserve_principal, initial)),
            "profit_lock_ratio": str(self._ratio(row.total_locked_transfer, max(realized, D("0")))),
            "profit_lock_high_water_mark": str(row.profit_lock_high_water_mark),
            "initial_capital_recovered": row.initial_capital_recovered_at is not None,
            "initial_capital_recovered_at": row.initial_capital_recovered_at,
            "last_trigger_at": row.last_trigger_at,
        }

    def transfers(self, account_id, limit=100, offset=0):
        return list(self.db.scalars(select(CapitalTransfer).where(
            CapitalTransfer.account_id == account_id,
        ).order_by(desc(CapitalTransfer.timestamp), desc(CapitalTransfer.id)).offset(offset).limit(limit)))

    def _allocate_core(self, row, amount, at):
        price = self._core_price(row.core_symbol, at)
        if price is None:
            row.core_pending_cash = D(str(row.core_pending_cash)) + amount
            return
        row.core_units = D(str(row.core_units)) + amount / price
        row.core_last_price = price

    def _core_price(self, symbol, at=None):
        query = select(MarketBar).where(MarketBar.symbol == "US." + symbol.upper())
        if at is not None:
            query = query.where(MarketBar.timestamp_utc <= at)
        bar = self.db.scalar(query.order_by(desc(MarketBar.timestamp_utc), desc(MarketBar.id)).limit(1))
        if bar is None or D(str(bar.close)) <= 0:
            return None
        return D(str(bar.close))

    def _transfer(self, account, state, destination, amount, realized, hwm, reason, at):
        key = "profit-lock:%s:%s:%s" % (account.id, str(hwm), destination)
        row = CapitalTransfer(
            transfer_id="PLM-%s-%s-%s" % (account.id, str(hwm).replace(".", "-"), destination),
            idempotency_key=key, account_id=account.id, timestamp=at,
            source_bucket="ACTIVE_TRADING", destination_bucket=destination,
            amount=amount, reason=reason, trigger_profit=realized,
            strategy_source="SYSTEM_PAPER", strategy_version="MIXED",
            allocation_rule_version=state.capital_management_version, status="ALLOCATED",
            metadata_json={"profit_lock_high_water_mark": str(hwm)},
        )
        self.db.add(row)
        self.db.flush()

    @staticmethod
    def _ratio(value, base):
        base = D(str(base))
        return D(str(value)) / base if base else D("0")

    @staticmethod
    def _empty_summary(account, initial):
        return {"status": "NOT_INITIALIZED", "capital_management_version": None,
                "initial_capital": str(initial), "active_trading_equity": str(account.total_equity),
                "active_available_cash": str(account.available_cash),
                "realized_strategy_profit": str(account.realized_pnl),
                "unrealized_strategy_profit": str(account.unrealized_pnl),
                "total_locked_transfer": "0", "reserve_principal": "0", "reserve_value": "0",
                "reserve_yield": "0", "reserve_mode": "CASH", "core_symbol": "SPY",
                "core_principal": "0", "core_value": "0", "core_pnl": "0", "core_units": "0",
                "core_pending_cash": "0", "total_wealth": str(account.total_equity),
                "capital_recovered_ratio": "0", "profit_lock_ratio": "0",
                "profit_lock_high_water_mark": "0", "initial_capital_recovered": False,
                "initial_capital_recovered_at": None, "last_trigger_at": None}
