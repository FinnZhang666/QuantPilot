from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.models import (
    CandidateSignal,
    MarketBar,
    SystemEquitySnapshot,
    SystemPaperAccount,
    SystemPaperFill,
    SystemPaperOrder,
    SystemPaperPosition,
    TradePlan,
    TradePlanTransition,
    UniverseInstrument,
)
from app.paper_runtime.audit import PaperAudit


D = Decimal
FILL_MODEL_VERSION = "paper-fill-v1"
EXIT_RULE_VERSION = "paper-exit-v1"


class PaperTradingService:
    """Deterministic, auditable paper ledger driven only by valid Trade Plans."""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.audit = PaperAudit(db)

    def account(self) -> SystemPaperAccount:
        row = self._stored_account()
        if row is None:
            initial = D(str(self.settings.paper_trading_initial_cash))
            row = SystemPaperAccount(
                account_key="system-paper", base_currency="USD", initial_cash=initial,
                available_cash=initial, reserved_cash=D("0"),
                position_market_value=D("0"), total_equity=initial,
                peak_equity=initial, max_drawdown=D("0"),
            )
            self.db.add(row)
            self.db.flush()
        return row

    def process_once(self, max_entries: Optional[int] = None) -> Dict[str, object]:
        if not self.settings.paper_trading_enabled:
            return {
                "status": "DISABLED", "opened": 0, "closed": 0,
                "partial": 0, "waiting": 0, "rejected": 0,
            }
        account = self.account()
        entries = self.evaluate_entries(account, max_entries=max_entries)
        exits = self.evaluate_exits(account)
        valuation = self.value_account(account, source="RUN_ONCE")
        self.db.commit()
        return {
            "status": "SUCCESS", **entries, **exits,
            "equity": str(valuation.total_equity),
        }

    def dry_run(self, max_entries: Optional[int] = None) -> Dict[str, object]:
        """Read-only eligibility evaluation. This method never flushes or commits."""
        account = self._stored_account()
        if account is None:
            initial = D(str(self.settings.paper_trading_initial_cash))
            account = SimpleNamespace(
                id=0, initial_cash=initial, available_cash=initial,
                reserved_cash=D("0"), total_equity=initial,
            )
        limit = max_entries or self.settings.paper_trading_max_entries_per_run
        plans = self._entry_plans()
        eligible: List[Dict[str, object]] = []
        rejected: List[Dict[str, object]] = []
        for plan in plans:
            decision = self._entry_decision(account, plan, mutate=False)
            item = {
                "trade_plan_id": plan.id, "plan_id": plan.plan_id,
                "symbol": plan.symbol, "direction": plan.direction,
                "result": decision["status"], "reason": decision.get("reason"),
                "rejection_code": decision.get("code"),
                "requested_price": self._text(decision.get("requested_price")),
                "quantity": self._text(decision.get("quantity")),
            }
            if decision["status"] == "READY":
                if len(eligible) < limit:
                    eligible.append(item)
                else:
                    item["result"] = "LIMITED"
                    item["rejection_code"] = "MAX_ENTRIES_PER_RUN"
                    item["reason"] = "Run limit reached"
                    rejected.append(item)
            else:
                rejected.append(item)
        return {
            "status": "DRY_RUN", "dry_run": True,
            "paper_trading_enabled": self.settings.paper_trading_enabled,
            "plans_scanned": len(plans), "eligible_trade_plans": len(eligible),
            "expected_orders": len(eligible), "max_entries": limit,
            "eligible": eligible, "rejected": rejected,
        }

    def evaluate_entries(
        self, account: SystemPaperAccount, max_entries: Optional[int] = None,
    ) -> Dict[str, int]:
        opened = waiting = rejected = 0
        limit = max_entries or self.settings.paper_trading_max_entries_per_run
        for plan in self._entry_plans():
            if opened >= limit:
                break
            self.audit.record(
                "CANDIDATE_EVALUATED", candidate_id=plan.signal_id,
                trade_plan_id=plan.id,
                details={"symbol": plan.symbol, "direction": plan.direction},
            )
            self.audit.record(
                "TRADE_PLAN_EVALUATED", candidate_id=plan.signal_id,
                trade_plan_id=plan.id,
                details={"stage": plan.lifecycle_stage, "status": plan.plan_status},
            )
            order, filled_now = self.create_entry_order(account, plan)
            if filled_now:
                opened += 1
            elif order.status.startswith("WAITING"):
                waiting += 1
            elif order.status == "REJECTED":
                rejected += 1
        return {"opened": opened, "waiting": waiting, "rejected": rejected}

    def create_entry_order(
        self, account: SystemPaperAccount, plan: TradePlan,
    ) -> Tuple[SystemPaperOrder, bool]:
        key = "paper-entry:%s:%s:%s" % (account.id, plan.id, plan.direction)
        existing = self.db.scalar(select(SystemPaperOrder).where(
            SystemPaperOrder.idempotency_key == key,
        ))
        if existing:
            return existing, self._retry_waiting_entry(account, plan, existing)

        decision = self._entry_decision(account, plan, mutate=True)
        requested = decision.get("requested_price") or D("0")
        order = SystemPaperOrder(
            account_id=account.id, trade_plan_id=plan.id, symbol=plan.symbol,
            market=plan.market, strategy_name=plan.strategy_name,
            strategy_version=plan.strategy_version, direction=plan.direction,
            order_side="BUY" if plan.direction == "LONG" else "SELL",
            order_type="LIMIT", requested_price=requested,
            quantity=decision.get("quantity") or D("0"),
            status=self._order_status(decision["status"]),
            source="TRADE_PLAN", idempotency_key=key,
            fill_model_version=FILL_MODEL_VERSION,
            rejection_code=decision.get("code"),
            metadata_json={
                "reason": decision.get("reason"),
                "timeframe": plan.timeframe,
                "trade_style": decision.get("trade_style"),
                "last_evaluated_bar": self._iso(decision.get("bar_timestamp")),
            },
        )
        self.db.add(order)
        self.db.flush()
        self.audit.record(
            "ORDER_CREATED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
            order_id=order.id,
            details={"status": order.status, "symbol": order.symbol, "side": order.order_side},
        )
        if order.status == "REJECTED":
            self.audit.record(
                "ORDER_REJECTED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
                order_id=order.id,
                details={"code": order.rejection_code, "reason": decision.get("reason")},
            )
        if decision["status"] == "READY":
            self._fill_entry(account, plan, order, decision["bar"], requested, decision["trade_style"])
        return order, order.status == "FILLED"

    def _retry_waiting_entry(
        self, account: SystemPaperAccount, plan: TradePlan, order: SystemPaperOrder,
    ) -> bool:
        if order.status not in {"WAITING_ENTRY", "WAITING_ENTRY_DATA"}:
            return False
        decision = self._entry_decision(account, plan, order=order, mutate=True)
        order.metadata_json = {
            "reason": decision.get("reason"), "timeframe": plan.timeframe,
            "trade_style": decision.get("trade_style"), "retried": True,
            "last_evaluated_bar": self._iso(decision.get("bar_timestamp")),
        }
        order.rejection_code = decision.get("code")
        order.requested_price = decision.get("requested_price") or D("0")
        order.quantity = decision.get("quantity") or D("0")
        order.status = self._order_status(decision["status"])
        if order.status == "REJECTED":
            self.audit.record(
                "ORDER_REJECTED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
                order_id=order.id,
                details={"code": order.rejection_code, "reason": decision.get("reason")},
            )
        if decision["status"] == "READY":
            self._fill_entry(
                account, plan, order, decision["bar"],
                decision["requested_price"], decision["trade_style"],
            )
        return order.status == "FILLED"

    def evaluate_exits(self, account: SystemPaperAccount) -> Dict[str, int]:
        closed = partial = updated = 0
        positions = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.account_id == account.id,
            SystemPaperPosition.status == "OPEN",
        ).order_by(SystemPaperPosition.id)))
        for position in positions:
            plan = self.db.get(TradePlan, position.trade_plan_id)
            if plan is None:
                continue
            for bar in self._unprocessed_bars(position, limit=1000):
                outcome = self._evaluate_position_bar(account, plan, position, bar)
                updated += 1
                if outcome == "PARTIAL":
                    partial += 1
                if outcome == "CLOSED":
                    closed += 1
                    break
        return {"closed": closed, "partial": partial, "positions_updated": updated}

    def value_account(
        self, account: SystemPaperAccount, source: str = "RUNTIME_VALUATION",
        valuation_time: Optional[datetime] = None,
    ) -> SystemPaperAccount:
        positions = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.account_id == account.id,
            SystemPaperPosition.status == "OPEN",
        )))
        now = valuation_time or datetime.now(timezone.utc)
        for position in positions:
            bar = self._latest_bar(position.symbol, position.timeframe)
            if bar is None:
                position.market_data_status = "MISSING"
                position.data_quality = "LOW"
                continue
            close = D(str(bar.close))
            position.current_price = close
            position.market_value = self._signed_market_value(position.direction, position.quantity, close)
            position.unrealized_pnl = self._pnl(
                position.direction, position.average_entry, close, position.quantity,
            )
            age = max(0, int((now - self._aware(bar.timestamp_utc)).total_seconds()))
            stale_after = (
                self.settings.paper_trading_stale_daily_seconds
                if position.timeframe == "1d"
                else self.settings.paper_trading_stale_intraday_seconds
            )
            position.market_data_status = "STALE" if age > stale_after else "CURRENT"
            position.data_quality = "MEDIUM" if position.market_data_status == "STALE" else "HIGH"

        position_value = sum((D(str(row.market_value)) for row in positions), D("0"))
        unrealized = sum((D(str(row.unrealized_pnl)) for row in positions), D("0"))
        equity = D(str(account.available_cash)) + D(str(account.reserved_cash)) + position_value
        account.position_market_value = position_value
        account.unrealized_pnl = unrealized
        account.total_equity = equity
        account.total_return = self._ratio(equity - D(str(account.initial_cash)), account.initial_cash)
        account.last_valuation_at = now

        first_today = self.db.scalar(select(SystemEquitySnapshot.equity).where(
            SystemEquitySnapshot.account_id == account.id,
            func.date(SystemEquitySnapshot.timestamp) == now.date().isoformat(),
        ).order_by(SystemEquitySnapshot.timestamp, SystemEquitySnapshot.id).limit(1))
        opening_equity = D(str(first_today if first_today is not None else equity))
        account.daily_pnl = equity - opening_equity
        daily_return = self._ratio(account.daily_pnl, opening_equity)
        peak = max(D(str(account.peak_equity or 0)), equity, D(str(account.initial_cash)))
        drawdown = self._ratio(equity - peak, peak)
        max_drawdown = min(D(str(account.max_drawdown or 0)), drawdown)
        account.peak_equity, account.max_drawdown = peak, max_drawdown

        latest = self.db.scalar(select(SystemEquitySnapshot).where(
            SystemEquitySnapshot.account_id == account.id,
        ).order_by(desc(SystemEquitySnapshot.timestamp), desc(SystemEquitySnapshot.id)).limit(1))
        if latest and all((
            D(str(latest.cash)) == D(str(account.available_cash)),
            D(str(latest.reserved_cash)) == D(str(account.reserved_cash)),
            D(str(latest.position_value)) == position_value,
            D(str(latest.equity)) == equity,
            D(str(latest.drawdown)) == drawdown,
            latest.source == source,
        )):
            return account
        snapshot = SystemEquitySnapshot(
            account_id=account.id, cash=account.available_cash,
            reserved_cash=account.reserved_cash, position_value=position_value,
            equity=equity, daily_pnl=account.daily_pnl, daily_return=daily_return,
            total_return=account.total_return, cumulative_return=account.total_return,
            peak_equity=peak, drawdown=drawdown, max_drawdown=max_drawdown, source=source,
        )
        self.db.add(snapshot)
        self.db.flush()
        self.audit.record(
            "EQUITY_UPDATED",
            details={"equity": str(equity), "drawdown": str(drawdown), "source": source},
        )
        return account

    def manual_close(
        self, position_id: int, reason: str = "MANUAL_CLOSE",
        quantity: Optional[Decimal] = None,
    ) -> SystemPaperPosition:
        if reason not in {"MANUAL_CLOSE", "SAFETY_CLOSE"}:
            raise ValueError("Manual close reason must be MANUAL_CLOSE or SAFETY_CLOSE.")
        account = self.account()
        position = self.db.get(SystemPaperPosition, position_id)
        if position is None or position.status != "OPEN":
            raise KeyError("Open system paper position not found.")
        plan = self.db.get(TradePlan, position.trade_plan_id)
        bar = self._latest_bar(position.symbol, position.timeframe)
        if plan is None or bar is None or self._aware(bar.timestamp_utc) < self._aware(position.open_time):
            raise ValueError("No valid persisted bar is available for manual close.")
        close_quantity = D(str(quantity)) if quantity is not None else D(str(position.quantity))
        if close_quantity <= 0 or close_quantity > D(str(position.quantity)):
            raise ValueError("Close quantity is outside the open position.")
        full = close_quantity == D(str(position.quantity))
        fill_price = self._adverse_market_fill(position.direction, D(str(bar.close)))
        self._execute_exit(
            account, plan, position, bar, close_quantity, fill_price, reason,
            trigger_price=D(str(bar.close)), full=full,
        )
        self.value_account(account, source="MANUAL_CLOSE")
        self.db.commit()
        return position

    def _entry_decision(
        self, account, plan: TradePlan, order: Optional[SystemPaperOrder] = None,
        mutate: bool = False,
    ) -> Dict[str, object]:
        candidate = self.db.get(CandidateSignal, plan.signal_id) if plan.signal_id else None
        if candidate is None:
            return self._decision("REJECTED", "MISSING_CANDIDATE", "Trade Plan has no persisted Candidate")
        if candidate.status != "VALID" or candidate.signal_type != "CANDIDATE_BUY":
            return self._decision("REJECTED", "INVALID_CANDIDATE", "Candidate is not a valid buy signal")
        if any((
            candidate.symbol.replace("US.", "") != plan.symbol.replace("US.", ""),
            candidate.timeframe != plan.timeframe,
            candidate.strategy_name != plan.strategy_name,
            candidate.strategy_version != plan.strategy_version,
        )):
            return self._decision("REJECTED", "CANDIDATE_MISMATCH", "Candidate snapshot does not match Trade Plan")
        if plan.direction not in {"LONG", "SHORT"}:
            return self._decision("REJECTED", "UNSUPPORTED_DIRECTION", "Direction is not supported")
        requested, trade_style = self._entry_price_and_style(plan)
        if requested is None or requested <= 0:
            return self._decision(
                "WAITING_ENTRY_DATA", "MISSING_ENTRY_PRICE", "Trade Plan has no executable entry price",
                trade_style=trade_style,
            )
        after = self._aware(plan.created_at)
        if order and order.metadata_json:
            previous = order.metadata_json.get("last_evaluated_bar")
            if previous:
                try:
                    after = self._aware(datetime.fromisoformat(previous))
                except ValueError:
                    pass
        bar = self._next_bar(plan.symbol, plan.timeframe, after)
        if bar is None:
            return self._decision(
                "WAITING_ENTRY_DATA", "MISSING_MARKET_BAR", "No unprocessed persisted bar after Trade Plan",
                requested_price=requested, trade_style=trade_style,
            )
        common = {
            "requested_price": requested, "trade_style": trade_style,
            "bar": bar, "bar_timestamp": bar.timestamp_utc,
        }
        if not self._entry_touched(plan, bar, requested, trade_style):
            return self._decision(
                "WAITING_ENTRY", "ENTRY_NOT_TRIGGERED", "Persisted bar did not trigger entry rule", **common,
            )
        limit_error = self._position_limit_error(account, plan, requested)
        if limit_error:
            return self._decision("REJECTED", limit_error[0], limit_error[1], **common)
        quantity, sizing_error = self._position_quantity(account, plan, requested)
        if sizing_error:
            return self._decision("REJECTED", sizing_error[0], sizing_error[1], **common)
        return self._decision("READY", None, None, quantity=quantity, **common)

    def _position_limit_error(self, account, plan, requested):
        open_positions = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.account_id == account.id,
            SystemPaperPosition.status == "OPEN",
        ))) if account.id else []
        if len(open_positions) >= self.settings.paper_trading_max_position_count:
            return "MAX_POSITION_COUNT", "Maximum paper position count reached"
        same_symbol = [row for row in open_positions if row.symbol == plan.symbol]
        if same_symbol and not self.settings.paper_trading_allow_same_symbol_multiple:
            return "DUPLICATE_SYMBOL", "An open position already exists for this symbol"
        if same_symbol and not self.settings.paper_trading_allow_strategy_coexistence:
            if any(row.strategy_name != plan.strategy_name for row in same_symbol):
                return "STRATEGY_COEXISTENCE_DISABLED", "Multiple strategies for one symbol are disabled"
        equity = D(str(account.total_equity))
        gross = sum((abs(D(str(row.quantity)) * D(str(row.current_price))) for row in open_positions), D("0"))
        if gross + requested > equity * D(str(self.settings.paper_trading_max_gross_exposure_pct)):
            return "MAX_GROSS_EXPOSURE", "Gross paper exposure limit reached"
        return None

    def _position_quantity(self, account, plan, requested):
        equity = D(str(account.total_equity))
        budget = (
            D(str(self.settings.paper_trading_fixed_cash_per_trade))
            if self.settings.paper_trading_sizing_mode == "FIXED_CASH"
            else equity * D(str(self.settings.paper_trading_position_pct))
        )
        if plan.strategy_name == "quality_mispricing_recovery":
            score_factor = D("1") if (plan.score or 0) >= 90 else (D("0.6") if (plan.score or 0) >= 80 else D("0.3"))
            budget = min(budget, equity * D(str(self.settings.qmr_target_position_pct)) * score_factor,
                         equity * D(str(self.settings.qmr_max_position_pct)))
        open_positions = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.account_id == account.id,
            SystemPaperPosition.status == "OPEN",
        ))) if account.id else []
        symbol_exposure = sum((
            abs(D(str(row.quantity)) * D(str(row.current_price)))
            for row in open_positions if row.symbol == plan.symbol
        ), D("0"))
        strategy_exposure = sum((
            abs(D(str(row.quantity)) * D(str(row.current_price)))
            for row in open_positions if row.strategy_name == plan.strategy_name
        ), D("0"))
        gross_exposure = sum((
            abs(D(str(row.quantity)) * D(str(row.current_price))) for row in open_positions
        ), D("0"))
        budget = min(
            budget,
            max(D("0"), equity * D(str(self.settings.paper_trading_max_symbol_exposure_pct)) - symbol_exposure),
            max(D("0"), equity * D(str(self.settings.paper_trading_max_strategy_exposure_pct)) - strategy_exposure),
            max(D("0"), equity * D(str(self.settings.paper_trading_max_gross_exposure_pct)) - gross_exposure),
        )
        if plan.strategy_name == "quality_mispricing_recovery":
            instrument = self.db.scalar(select(UniverseInstrument).where(
                UniverseInstrument.symbol == plan.symbol.replace("US.", "")))
            sector = instrument.sector if instrument else None
            if sector:
                sector_symbols = list(self.db.scalars(select(UniverseInstrument.symbol).where(
                    UniverseInstrument.sector == sector)))
                sector_exposure = sum((abs(D(str(row.quantity)) * D(str(row.current_price)))
                    for row in open_positions if row.symbol.replace("US.", "") in sector_symbols), D("0"))
                budget = min(budget, max(D("0"), equity * D(str(self.settings.qmr_max_sector_exposure)) - sector_exposure))
        if plan.direction == "LONG":
            minimum_cash = equity * D(str(self.settings.paper_trading_min_cash_reserve_pct))
            spendable = D(str(account.available_cash)) - minimum_cash - D(str(self.settings.paper_trading_fee_per_order))
            budget = min(budget, max(D("0"), spendable))
        quantity = budget / requested if requested else D("0")
        if not self.settings.paper_trading_allow_fractional:
            quantity = quantity.quantize(D("1"), rounding=ROUND_DOWN)
        if quantity <= 0:
            return D("0"), ("INSUFFICIENT_PAPER_CASH", "Insufficient paper cash or exposure capacity")
        return quantity, None

    def _fill_entry(self, account, plan, order, bar, requested, trade_style):
        slippage = requested * D(str(self.settings.paper_trading_slippage_bps)) / D("10000")
        fill_price = requested + slippage if plan.direction == "LONG" else requested - slippage
        if fill_price <= 0:
            self._reject(order, plan, "INVALID_FILL_PRICE", "Conservative fill price is invalid")
            return
        fee = D(str(self.settings.paper_trading_fee_per_order))
        notional = fill_price * D(str(order.quantity))
        if plan.direction == "LONG":
            minimum_cash = D(str(account.total_equity)) * D(str(self.settings.paper_trading_min_cash_reserve_pct))
            if D(str(account.available_cash)) - notional - fee < minimum_cash:
                self._reject(order, plan, "MINIMUM_CASH_RESERVE", "Entry would breach minimum cash reserve")
                return
            account.available_cash = D(str(account.available_cash)) - notional - fee
        else:
            account.available_cash = D(str(account.available_cash)) + notional - fee
        timestamp = self._aware(bar.timestamp_utc)
        order.status, order.filled_at = "FILLED", timestamp
        fill = SystemPaperFill(
            order_id=order.id, price=fill_price, quantity=order.quantity,
            timestamp=timestamp, bar_timestamp=timestamp, slippage=slippage,
            fee=fee, source="HISTORICAL_BAR",
        )
        self.db.add(fill)
        self.db.flush()
        position = SystemPaperPosition(
            account_id=account.id, trade_plan_id=plan.id, opening_order_id=order.id,
            symbol=plan.symbol, market=plan.market, direction=plan.direction,
            strategy_name=plan.strategy_name, strategy_version=plan.strategy_version,
            trade_style=trade_style, timeframe=plan.timeframe,
            quantity=order.quantity, initial_quantity=order.quantity,
            average_entry=fill_price, open_time=timestamp, entry_bar_timestamp=timestamp,
            current_price=fill_price,
            market_value=self._signed_market_value(plan.direction, order.quantity, fill_price),
            stop_price=plan.stop_loss_price, targets_json=plan.target_prices_json or [],
            highest_price=fill_price, lowest_price=fill_price,
            fill_model_version=FILL_MODEL_VERSION, exit_rule_version=EXIT_RULE_VERSION,
            last_market_timestamp=timestamp, market_data_status="CURRENT",
            data_quality="HIGH", status="OPEN",
        )
        self.db.add(position)
        self.db.flush()
        self.audit.record(
            "FILL_CREATED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
            order_id=order.id, fill_id=fill.id,
            details={"price": str(fill_price), "quantity": str(order.quantity)},
        )
        self.audit.record(
            "POSITION_OPENED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
            order_id=order.id, fill_id=fill.id, position_id=position.id,
            details={"symbol": plan.symbol, "direction": plan.direction},
        )
        self._transition(plan, "COMPANION", "System paper entry filled")

    def _evaluate_position_bar(self, account, plan, position, bar):
        open_price, high, low, close = map(
            lambda value: D(str(value)), (bar.open, bar.high, bar.low, bar.close),
        )
        if min(open_price, high, low, close) <= 0 or low > high:
            position.market_data_status = "INVALID"
            position.data_quality = "LOW"
            return "UPDATED"
        position.highest_price = max(D(str(position.highest_price)), high)
        position.lowest_price = min(D(str(position.lowest_price)), low)
        entry = D(str(position.average_entry))
        if position.direction == "LONG":
            position.mfe = max(D(str(position.mfe)), self._ratio(position.highest_price - entry, entry))
            position.mae = min(D(str(position.mae)), self._ratio(position.lowest_price - entry, entry))
        else:
            position.mfe = max(D(str(position.mfe)), self._ratio(entry - position.lowest_price, entry))
            position.mae = min(D(str(position.mae)), self._ratio(entry - position.highest_price, entry))
        position.current_price = close
        position.market_value = self._signed_market_value(position.direction, position.quantity, close)
        position.unrealized_pnl = self._pnl(position.direction, entry, close, position.quantity)
        position.last_market_timestamp = self._aware(bar.timestamp_utc)
        position.market_data_status, position.data_quality = "CURRENT", "HIGH"
        position.bars_held += 1

        stop = D(str(position.stop_price)) if position.stop_price is not None else None
        target = self._target(position)
        stop_hit = stop is not None and (
            low <= stop if position.direction == "LONG" else high >= stop
        )
        target_hit = target is not None and (
            high >= target if position.direction == "LONG" else low <= target
        )
        if stop_hit:
            ambiguous = target_hit
            fill_price = self._stop_fill(position.direction, stop, open_price)
            self._execute_exit(
                account, plan, position, bar, D(str(position.quantity)), fill_price,
                "AMBIGUOUS_STOP_PRIORITY" if ambiguous else "STOP_LOSS",
                trigger_price=stop, full=True,
            )
            return "CLOSED"
        qmr_outcome = self._evaluate_qmr_exit(account, plan, position, bar)
        if qmr_outcome:
            return qmr_outcome
        if target_hit:
            targets = position.targets_json or []
            final_target = position.target_index >= len(targets) - 1
            quantity = D(str(position.quantity))
            if not final_target:
                quantity *= D(str(self.settings.paper_trading_target1_reduce_pct))
                if not self.settings.paper_trading_allow_fractional:
                    quantity = quantity.quantize(D("1"), rounding=ROUND_DOWN)
                if quantity <= 0 or quantity >= D(str(position.quantity)):
                    final_target = True
                    quantity = D(str(position.quantity))
            fill_price = self._target_fill(position.direction, target)
            reason = "TARGET_%s" % (position.target_index + 1)
            if not final_target:
                reason += "_PARTIAL"
            self._execute_exit(
                account, plan, position, bar, quantity, fill_price, reason,
                trigger_price=target, full=final_target,
            )
            return "CLOSED" if final_target else "PARTIAL"
        if plan.lifecycle_stage in {"CANCELLED", "EXPIRED"}:
            reason = "CANCELLED" if plan.lifecycle_stage == "CANCELLED" else "EXPIRED"
            self._execute_exit(
                account, plan, position, bar, D(str(position.quantity)),
                self._adverse_market_fill(position.direction, close), reason,
                trigger_price=close, full=True,
            )
            return "CLOSED"
        if self.settings.paper_trading_max_holding_bars:
            if position.bars_held >= self.settings.paper_trading_max_holding_bars:
                self._execute_exit(
                    account, plan, position, bar, D(str(position.quantity)),
                    self._adverse_market_fill(position.direction, close), "MAX_HOLDING_PERIOD",
                    trigger_price=close, full=True,
                )
                return "CLOSED"
        self.audit.record(
            "POSITION_UPDATED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
            position_id=position.id,
            details={"bar_timestamp": self._iso(bar.timestamp_utc), "current_price": str(close)},
        )
        return "UPDATED"

    def _evaluate_qmr_exit(self, account, plan, position, bar):
        """Execute only state transitions in the internal paper ledger, never a broker account."""
        if not (
            getattr(self.settings, "qmr_exit_enabled", False)
            and getattr(self.settings, "qmr_paper_auto_trading", False)
        ):
            return None
        qmr_names = {"quality_mispricing_recovery", "优质错杀修复", "QMR"}
        if position.strategy_name not in qmr_names:
            return None
        from app.qmr_exit.service import QmrExitService
        service = QmrExitService(self.db, self.settings)
        at = self._aware(bar.timestamp_utc)
        result = service.evaluate_position(position, at)
        service.persist(position, at, result)
        if result["state"] not in {"REDUCE", "EXIT"} or result["state"] == result["previous_state"]:
            return None
        quantity = D(str(position.quantity))
        full = result["state"] == "EXIT"
        if not full:
            quantity *= D(str(result["reduce_ratio"] or self.settings.paper_trading_target1_reduce_pct))
            if not self.settings.paper_trading_allow_fractional:
                quantity = quantity.quantize(D("1"), rounding=ROUND_DOWN)
            if quantity <= 0 or quantity >= D(str(position.quantity)):
                full, quantity = True, D(str(position.quantity))
        self._execute_exit(
            account, plan, position, bar, quantity,
            self._adverse_market_fill(position.direction, D(str(bar.close))),
            "QMR_EXIT" if full else "QMR_REDUCE", trigger_price=D(str(bar.close)), full=full,
        )
        return "CLOSED" if full else "PARTIAL"

    def _execute_exit(
        self, account, plan, position, bar, quantity, fill_price, reason,
        trigger_price, full,
    ):
        timestamp = self._aware(bar.timestamp_utc)
        key = "paper-exit:%s:%s:%s:%s:%s" % (
            account.id, position.id, reason, timestamp.isoformat(), position.target_index,
        )
        existing = self.db.scalar(select(SystemPaperOrder).where(
            SystemPaperOrder.idempotency_key == key,
        ))
        if existing:
            return existing
        fee = D(str(self.settings.paper_trading_fee_per_order))
        exit_order = SystemPaperOrder(
            account_id=account.id, trade_plan_id=plan.id, symbol=plan.symbol,
            market=plan.market, strategy_name=plan.strategy_name,
            strategy_version=plan.strategy_version, direction=plan.direction,
            order_side="SELL" if position.direction == "LONG" else "BUY",
            order_type="SYSTEM_EXIT", requested_price=trigger_price,
            trigger_price=trigger_price, trigger_bar_timestamp=timestamp,
            quantity=quantity, status="FILLED", source="EXIT_EVALUATION",
            idempotency_key=key, fill_model_version=FILL_MODEL_VERSION,
            rule_version=EXIT_RULE_VERSION, filled_at=timestamp,
            metadata_json={
                "position_id": position.id, "exit_reason": reason,
                "full_exit": full, "rule_version": EXIT_RULE_VERSION,
            },
        )
        self.db.add(exit_order)
        self.db.flush()
        fill = SystemPaperFill(
            order_id=exit_order.id, price=fill_price, quantity=quantity,
            timestamp=timestamp, bar_timestamp=timestamp,
            slippage=abs(fill_price - D(str(trigger_price))), fee=fee,
            source="EXIT_EVALUATION",
        )
        self.db.add(fill)
        self.db.flush()
        entry_fee = self.db.scalar(select(SystemPaperFill.fee).where(
            SystemPaperFill.order_id == position.opening_order_id,
        )) or D("0")
        initial_quantity = D(str(position.initial_quantity or position.quantity))
        allocated_entry_fee = D(str(entry_fee)) * self._ratio(quantity, initial_quantity)
        pnl = self._pnl(position.direction, position.average_entry, fill_price, quantity)
        pnl -= fee + allocated_entry_fee
        if position.direction == "LONG":
            account.available_cash = D(str(account.available_cash)) + quantity * fill_price - fee
        else:
            account.available_cash = D(str(account.available_cash)) - quantity * fill_price - fee
        account.realized_pnl = D(str(account.realized_pnl)) + pnl
        position.realized_pnl = D(str(position.realized_pnl)) + pnl
        remaining = D(str(position.quantity)) - quantity
        position.last_exit_trigger_price = trigger_price
        position.last_exit_trigger_bar = timestamp
        position.closing_order_id = exit_order.id
        position.exit_price, position.exit_reason = fill_price, reason
        self.audit.record(
            "FILL_CREATED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
            order_id=exit_order.id, fill_id=fill.id, position_id=position.id,
            details={"price": str(fill_price), "quantity": str(quantity), "reason": reason},
        )
        if full or remaining <= 0:
            position.quantity = D("0")
            position.unrealized_pnl = D("0")
            position.current_price, position.market_value = fill_price, D("0")
            position.status, position.close_time = "CLOSED", timestamp
            self.audit.record(
                "POSITION_CLOSED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
                order_id=exit_order.id, fill_id=fill.id, position_id=position.id,
                details={"reason": reason, "realized_pnl": str(position.realized_pnl)},
            )
            self._transition(plan, "REVIEW", "System paper position closed: " + reason)
            plan.review_status = "PENDING"
        else:
            position.quantity = remaining
            if reason.startswith("TARGET_"):
                position.target_index += 1
            position.market_value = self._signed_market_value(
                position.direction, remaining, position.current_price,
            )
            position.unrealized_pnl = self._pnl(
                position.direction, position.average_entry, position.current_price, remaining,
            )
            self.audit.record(
                "POSITION_UPDATED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
                order_id=exit_order.id, fill_id=fill.id, position_id=position.id,
                details={"reason": reason, "remaining_quantity": str(remaining)},
            )
        return exit_order

    def _reject(self, order, plan, code, reason):
        order.status, order.rejection_code = "REJECTED", code
        order.metadata_json = {"reason": reason}
        self.audit.record(
            "ORDER_REJECTED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
            order_id=order.id, details={"code": code, "reason": reason},
        )

    def _entry_plans(self):
        return list(self.db.scalars(select(TradePlan).where(
            TradePlan.lifecycle_stage == "PLAN", TradePlan.plan_status == "ACTIVE",
        ).order_by(TradePlan.created_at, TradePlan.id)))

    def _stored_account(self):
        return self.db.scalar(select(SystemPaperAccount).where(
            SystemPaperAccount.account_key == "system-paper",
        ))

    def _unprocessed_bars(self, position, limit):
        after = position.last_market_timestamp or position.open_time
        symbol = position.symbol if position.symbol.startswith("US.") else "US." + position.symbol
        return list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol == symbol, MarketBar.interval == position.timeframe,
            MarketBar.timestamp_utc > after,
        ).order_by(MarketBar.timestamp_utc, MarketBar.id).limit(limit)))

    def _next_bar(self, symbol, interval, after):
        full = symbol if symbol.startswith("US.") else "US." + symbol
        return self.db.scalar(select(MarketBar).where(
            MarketBar.symbol == full, MarketBar.interval == interval,
            MarketBar.timestamp_utc > after,
        ).order_by(MarketBar.timestamp_utc, MarketBar.id).limit(1))

    def _latest_bar(self, symbol, interval):
        full = symbol if symbol.startswith("US.") else "US." + symbol
        return self.db.scalar(select(MarketBar).where(
            MarketBar.symbol == full, MarketBar.interval == interval,
        ).order_by(desc(MarketBar.timestamp_utc), desc(MarketBar.id)).limit(1))

    @staticmethod
    def _entry_price_and_style(plan):
        if plan.breakout_zone_lower is not None and plan.breakout_zone_upper is not None:
            price = plan.breakout_zone_upper if plan.direction == "LONG" else plan.breakout_zone_lower
            return D(str(price)), "BREAKOUT"
        if plan.buy_zone_lower is not None and plan.buy_zone_upper is not None:
            price = plan.buy_zone_upper if plan.direction == "LONG" else plan.buy_zone_lower
            return D(str(price)), "PULLBACK"
        if plan.reference_price is not None:
            return D(str(plan.reference_price)), "REFERENCE"
        return None, "PULLBACK"

    @staticmethod
    def _entry_touched(plan, bar, requested, trade_style):
        low, high = D(str(bar.low)), D(str(bar.high))
        if trade_style == "BREAKOUT":
            return high >= requested if plan.direction == "LONG" else low <= requested
        if plan.buy_zone_lower is not None and plan.buy_zone_upper is not None:
            lower, upper = D(str(plan.buy_zone_lower)), D(str(plan.buy_zone_upper))
            return low <= upper and high >= lower
        return low <= requested <= high

    @staticmethod
    def _decision(status, code, reason, **extra):
        return {"status": status, "code": code, "reason": reason, **extra}

    @staticmethod
    def _order_status(status):
        return {
            "READY": "PENDING", "WAITING_ENTRY": "WAITING_ENTRY",
            "WAITING_ENTRY_DATA": "WAITING_ENTRY_DATA", "REJECTED": "REJECTED",
        }[status]

    @staticmethod
    def _target(position):
        values = position.targets_json or []
        if position.target_index >= len(values):
            return None
        return D(str(values[position.target_index]))

    def _stop_fill(self, direction, stop, bar_open):
        slippage = stop * D(str(self.settings.paper_trading_slippage_bps)) / D("10000")
        if direction == "LONG":
            return max(D("0.00000001"), min(stop, bar_open) - slippage)
        return max(stop, bar_open) + slippage

    def _target_fill(self, direction, target):
        slippage = target * D(str(self.settings.paper_trading_slippage_bps)) / D("10000")
        if direction == "LONG":
            return max(D("0.00000001"), target - slippage)
        return target + slippage

    def _adverse_market_fill(self, direction, close):
        slippage = close * D(str(self.settings.paper_trading_slippage_bps)) / D("10000")
        return close - slippage if direction == "LONG" else close + slippage

    @staticmethod
    def _signed_market_value(direction, quantity, price):
        value = D(str(quantity)) * D(str(price))
        return value if direction == "LONG" else -value

    @staticmethod
    def _pnl(direction, entry, price, quantity):
        entry, price, quantity = D(str(entry)), D(str(price)), D(str(quantity))
        return quantity * (price - entry) if direction == "LONG" else quantity * (entry - price)

    @staticmethod
    def _ratio(numerator, denominator):
        denominator = D(str(denominator))
        return D(str(numerator)) / denominator if denominator else D("0")

    @staticmethod
    def _text(value):
        return None if value is None else str(value)

    @staticmethod
    def _iso(value):
        return value.isoformat() if value is not None else None

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

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
