from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import (
    MarketBar, SystemEquitySnapshot, SystemPaperAccount, SystemPaperFill,
    SystemPaperOrder, SystemPaperPosition, TradePlan, TradePlanTransition,
)


D = Decimal


class PaperTradingService:
    """Deterministic system-only paper ledger driven exclusively by Trade Plans."""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def account(self) -> SystemPaperAccount:
        row = self.db.scalar(select(SystemPaperAccount).where(
            SystemPaperAccount.account_key == "system-paper",
        ))
        if row is None:
            initial = D(str(self.settings.paper_trading_initial_cash))
            row = SystemPaperAccount(
                account_key="system-paper", base_currency="USD", initial_cash=initial,
                available_cash=initial, reserved_cash=D("0"),
                position_market_value=D("0"), total_equity=initial,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def process_once(self):
        if not self.settings.paper_trading_enabled:
            return {"status": "DISABLED", "opened": 0, "closed": 0, "waiting": 0}
        account = self.account()
        opened = waiting = 0
        plans = list(self.db.scalars(select(TradePlan).where(
            TradePlan.lifecycle_stage.in_(["PLAN", "COMPANION"]),
            TradePlan.plan_status == "ACTIVE",
        ).order_by(TradePlan.created_at, TradePlan.id)))
        for plan in plans:
            if self.db.scalar(select(SystemPaperPosition.id).where(
                SystemPaperPosition.trade_plan_id == plan.id,
                SystemPaperPosition.status == "OPEN",
            )):
                continue
            order, filled_now = self.create_entry_order(account, plan)
            if filled_now:
                opened += 1
            elif order.status.startswith("WAITING"):
                waiting += 1
        closed = self.evaluate_exits(account)
        self.value_account(account)
        self.db.commit()
        return {"status": "SUCCESS", "opened": opened, "closed": closed, "waiting": waiting}

    def create_entry_order(self, account: SystemPaperAccount, plan: TradePlan):
        key = "paper-entry:%s:%s:%s" % (account.id, plan.id, plan.direction)
        existing = self.db.scalar(select(SystemPaperOrder).where(
            SystemPaperOrder.idempotency_key == key,
        ))
        if existing:
            return existing, self._retry_waiting_entry(account, plan, existing)
        requested = self._entry_price(plan)
        status, reason = "PENDING", None
        if plan.direction != "LONG":
            status, reason = "WAITING_UNSUPPORTED_DIRECTION", "paper-fill-v1 supports LONG entry only"
        elif requested is None:
            status, reason = "WAITING_ENTRY_DATA", "Trade Plan has no persisted entry price"
        bar = self._latest_bar(plan.symbol, plan.timeframe)
        if status == "PENDING" and bar is None:
            status, reason = "WAITING_ENTRY_DATA", "No matching persisted bar"
        if status == "PENDING" and self._aware(bar.timestamp_utc) < self._aware(plan.created_at):
            status, reason = "WAITING_ENTRY_DATA", "Latest persisted bar predates Trade Plan"
        quantity = D("0")
        if status == "PENDING":
            budget = D(str(account.total_equity)) * D(str(self.settings.paper_trading_position_pct))
            quantity = budget / requested
            if not self.settings.paper_trading_allow_fractional:
                quantity = quantity.quantize(D("1"), rounding=ROUND_DOWN)
            notional = quantity * requested
            if quantity <= 0 or notional > D(str(account.available_cash)):
                status, reason = "REJECTED", "Insufficient paper cash"
            elif not self._entry_touched(plan, bar, requested):
                status, reason = "WAITING_ENTRY", "Persisted bar did not touch entry rule"
        order = SystemPaperOrder(
            account_id=account.id, trade_plan_id=plan.id, symbol=plan.symbol,
            market=plan.market, strategy_name=plan.strategy_name,
            strategy_version=plan.strategy_version, direction=plan.direction,
            order_side="BUY", order_type="LIMIT", requested_price=requested or D("0"),
            quantity=quantity, status=status, idempotency_key=key,
            metadata_json={"reason": reason, "timeframe": plan.timeframe},
        )
        self.db.add(order)
        self.db.flush()
        if status == "PENDING":
            self._fill_entry(account, plan, order, bar, requested)
        return order, order.status == "FILLED"

    def _retry_waiting_entry(self, account, plan, order):
        if order.status not in {"WAITING_ENTRY", "WAITING_ENTRY_DATA"}:
            return False
        requested = self._entry_price(plan)
        bar = self._latest_bar(plan.symbol, plan.timeframe)
        if requested is None or bar is None:
            return False
        if self._aware(bar.timestamp_utc) < self._aware(plan.created_at):
            return False
        if not self._entry_touched(plan, bar, requested):
            order.status = "WAITING_ENTRY"
            return False
        budget = D(str(account.total_equity)) * D(str(self.settings.paper_trading_position_pct))
        quantity = budget / requested
        if not self.settings.paper_trading_allow_fractional:
            quantity = quantity.quantize(D("1"), rounding=ROUND_DOWN)
        if quantity <= 0 or quantity * requested > D(str(account.available_cash)):
            order.status = "REJECTED"
            order.metadata_json = {"reason": "Insufficient paper cash"}
            return False
        order.requested_price, order.quantity, order.status = requested, quantity, "PENDING"
        order.metadata_json = {"reason": None, "timeframe": plan.timeframe, "retried": True}
        self._fill_entry(account, plan, order, bar, requested)
        return order.status == "FILLED"

    def evaluate_exits(self, account: SystemPaperAccount) -> int:
        closed = 0
        positions = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.account_id == account.id,
            SystemPaperPosition.status == "OPEN",
        )))
        for position in positions:
            plan = self.db.get(TradePlan, position.trade_plan_id)
            bar = self._latest_bar(position.symbol, plan.timeframe)
            if bar is None or self._aware(bar.timestamp_utc) <= self._aware(position.open_time):
                continue
            high, low, close = map(lambda value: D(str(value)), (bar.high, bar.low, bar.close))
            position.highest_price = max(D(str(position.highest_price)), high)
            position.lowest_price = min(D(str(position.lowest_price)), low)
            entry = D(str(position.average_entry))
            position.mfe = max(D(str(position.mfe)), (position.highest_price - entry) / entry)
            position.mae = min(D(str(position.mae)), (position.lowest_price - entry) / entry)
            target = self._first_target(position.targets_json)
            stop = D(str(position.stop_price)) if position.stop_price is not None else None
            # Conservative v1 rule: stop wins when stop and target occur in the same bar.
            if stop is not None and low <= stop:
                self._close(account, plan, position, bar, stop, "STOP_LOSS")
                closed += 1
            elif target is not None and high >= target:
                self._close(account, plan, position, bar, target, "TAKE_PROFIT")
                closed += 1
            else:
                position.current_price = close
                position.market_value = position.quantity * close
                position.unrealized_pnl = position.quantity * (close - entry)
        return closed

    def value_account(self, account: SystemPaperAccount):
        positions = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.account_id == account.id,
            SystemPaperPosition.status == "OPEN",
        )))
        position_value = sum((D(str(row.market_value)) for row in positions), D("0"))
        unrealized = sum((D(str(row.unrealized_pnl)) for row in positions), D("0"))
        equity = D(str(account.available_cash)) + D(str(account.reserved_cash)) + position_value
        account.position_market_value = position_value
        account.unrealized_pnl = unrealized
        account.total_equity = equity
        account.total_return = (equity - D(str(account.initial_cash))) / D(str(account.initial_cash))
        account.last_valuation_at = datetime.now(timezone.utc)
        first_today = self.db.scalar(select(SystemEquitySnapshot.equity).where(
            SystemEquitySnapshot.account_id == account.id,
            func.date(SystemEquitySnapshot.timestamp) == account.last_valuation_at.date().isoformat(),
        ).order_by(SystemEquitySnapshot.timestamp, SystemEquitySnapshot.id).limit(1))
        account.daily_pnl = equity - D(str(first_today if first_today is not None else equity))
        peak = self.db.scalar(select(func.max(SystemEquitySnapshot.equity)).where(
            SystemEquitySnapshot.account_id == account.id,
        ))
        peak = max(D(str(peak or equity)), equity)
        drawdown = (equity - peak) / peak if peak else D("0")
        latest = self.db.scalar(select(SystemEquitySnapshot).where(
            SystemEquitySnapshot.account_id == account.id,
        ).order_by(desc(SystemEquitySnapshot.timestamp), desc(SystemEquitySnapshot.id)).limit(1))
        if latest and all((
            D(str(latest.cash)) == D(str(account.available_cash)),
            D(str(latest.reserved_cash)) == D(str(account.reserved_cash)),
            D(str(latest.position_value)) == position_value,
            D(str(latest.equity)) == equity,
            D(str(latest.drawdown)) == drawdown,
        )):
            return account
        self.db.add(SystemEquitySnapshot(
            account_id=account.id, cash=account.available_cash,
            reserved_cash=account.reserved_cash, position_value=position_value,
            equity=equity, daily_pnl=account.daily_pnl,
            total_return=account.total_return, drawdown=drawdown,
        ))
        return account

    def _fill_entry(self, account, plan, order, bar, price):
        slippage = price * D(str(self.settings.paper_trading_slippage_bps)) / D("10000")
        fill_price = price + slippage
        fee = D(str(self.settings.paper_trading_fee_per_order))
        total = fill_price * order.quantity + fee
        if total > D(str(account.available_cash)):
            order.status = "REJECTED"
            order.metadata_json = {"reason": "Insufficient paper cash after costs"}
            return
        now = self._aware(bar.timestamp_utc)
        order.status, order.filled_at = "FILLED", now
        self.db.add(SystemPaperFill(
            order_id=order.id, price=fill_price, quantity=order.quantity,
            timestamp=now, bar_timestamp=now, slippage=slippage, fee=fee,
        ))
        account.available_cash = D(str(account.available_cash)) - total
        self.db.add(SystemPaperPosition(
            account_id=account.id, trade_plan_id=plan.id, opening_order_id=order.id,
            symbol=plan.symbol, market=plan.market, direction=plan.direction,
            strategy_name=plan.strategy_name, strategy_version=plan.strategy_version,
            quantity=order.quantity, average_entry=fill_price, open_time=now,
            current_price=fill_price, market_value=fill_price * order.quantity,
            stop_price=plan.stop_loss_price, targets_json=plan.target_prices_json or [],
            highest_price=fill_price, lowest_price=fill_price, status="OPEN",
        ))
        self._transition(plan, "COMPANION", "Paper entry filled")

    def _close(self, account, plan, position, bar, price, reason):
        fee = D(str(self.settings.paper_trading_fee_per_order))
        proceeds = position.quantity * price - fee
        pnl = position.quantity * (price - position.average_entry) - fee
        closed_at = self._aware(bar.timestamp_utc)
        exit_order = SystemPaperOrder(
            account_id=account.id, trade_plan_id=plan.id, symbol=plan.symbol,
            market=plan.market, strategy_name=plan.strategy_name,
            strategy_version=plan.strategy_version, direction=plan.direction,
            order_side="SELL", order_type="SYSTEM_EXIT", requested_price=price,
            quantity=position.quantity, status="FILLED", source="EXIT_EVALUATION",
            idempotency_key="paper-exit:%s:%s" % (account.id, position.id),
            fill_model_version="paper-fill-v1", filled_at=closed_at,
            metadata_json={"position_id": position.id, "exit_reason": reason},
        )
        self.db.add(exit_order); self.db.flush()
        self.db.add(SystemPaperFill(
            order_id=exit_order.id, price=price, quantity=position.quantity,
            timestamp=closed_at, bar_timestamp=closed_at, slippage=D("0"), fee=fee,
            source="EXIT_EVALUATION",
        ))
        account.available_cash = D(str(account.available_cash)) + proceeds
        account.realized_pnl = D(str(account.realized_pnl)) + pnl
        position.realized_pnl, position.unrealized_pnl = pnl, D("0")
        position.current_price, position.market_value = price, D("0")
        position.status, position.close_time = "CLOSED", closed_at
        position.closing_order_id = exit_order.id
        position.exit_price, position.exit_reason = price, reason
        self._transition(plan, "REVIEW", "Paper position closed: " + reason)
        plan.review_status = "PENDING"

    def _transition(self, plan, target, reason):
        if plan.lifecycle_stage == target:
            return
        previous = plan.lifecycle_stage
        plan.lifecycle_stage = target
        self.db.add(TradePlanTransition(
            trade_plan_id=plan.id, previous_stage=previous, new_stage=target,
            transitioned_at=datetime.now(timezone.utc), reason=reason,
            source="PAPER_RUNTIME", metadata_json={"paper": True},
        ))

    def _latest_bar(self, symbol, interval):
        full = symbol if symbol.startswith("US.") else "US." + symbol
        return self.db.scalar(select(MarketBar).where(
            MarketBar.symbol == full, MarketBar.interval == interval,
        ).order_by(desc(MarketBar.timestamp_utc), desc(MarketBar.id)).limit(1))

    @staticmethod
    def _entry_price(plan) -> Optional[Decimal]:
        if plan.buy_zone_lower is not None and plan.buy_zone_upper is not None:
            return (D(str(plan.buy_zone_lower)) + D(str(plan.buy_zone_upper))) / D("2")
        return D(str(plan.reference_price)) if plan.reference_price is not None else None

    @staticmethod
    def _entry_touched(plan, bar, requested):
        low, high = D(str(bar.low)), D(str(bar.high))
        if plan.buy_zone_lower is not None and plan.buy_zone_upper is not None:
            return low <= D(str(plan.buy_zone_upper)) and high >= D(str(plan.buy_zone_lower))
        return low <= requested <= high

    @staticmethod
    def _first_target(values):
        return D(str(values[0])) if values else None

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
