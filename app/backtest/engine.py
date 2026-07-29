from decimal import Decimal, ROUND_FLOOR
from typing import Dict, List, Optional

from app.backtest.fees import adjusted_price, commission
from app.backtest.metrics import calculate_metrics
from app.backtest.models import (
    ActionType, BacktestBar, BacktestConfig, BacktestResult, BacktestSignal,
    EquityPoint, PendingAction, PositionState, TradeResult,
)
from app.backtest.quality import validate_inputs


class BacktestEngine:
    """Deterministic long-only simulator. It never imports an execution or broker module."""

    def run(
        self, config: BacktestConfig, bars: List[BacktestBar],
        signals: List[BacktestSignal],
    ) -> BacktestResult:
        selected = [bar for bar in bars if config.start_time <= bar.timestamp <= config.end_time]
        selected_signals = [
            signal for signal in signals
            if config.start_time <= signal.timestamp <= config.end_time
        ]
        errors = validate_inputs(config, selected, selected_signals)
        if errors:
            return BacktestResult(
                status="FAILED", bars_processed=0, signals_processed=0,
                ending_cash=config.initial_cash, ending_equity=config.initial_cash, errors=errors,
            )
        if len(selected) < 20:
            return BacktestResult(
                status="INSUFFICIENT_DATA", bars_processed=len(selected),
                signals_processed=len(selected_signals), ending_cash=config.initial_cash,
                ending_equity=config.initial_cash,
                errors=["INSUFFICIENT_BACKTEST_DATA：正式区间至少需要20根K线。"],
            )

        signal_map: Dict[object, BacktestSignal] = {signal.timestamp: signal for signal in selected_signals}
        cash = config.initial_cash
        shares = 0
        state = PositionState.FLAT
        pending: Optional[PendingAction] = None
        pending_rows: List[PendingAction] = []
        trades: List[TradeResult] = []
        current_trade: Optional[TradeResult] = None
        holding_bars: List[BacktestBar] = []
        points: List[EquityPoint] = []
        peak = config.initial_cash

        for index, bar in enumerate(selected):
            if pending is not None:
                raw = bar.open
                if raw <= 0:
                    pending.status = "INVALID_EXECUTION_PRICE"
                    pending.failure_reason = "下一根K线开盘价无效。"
                    pending = None
                elif pending.action_type == ActionType.ENTER_LONG_PENDING:
                    price = adjusted_price(raw, config.slippage_bps, True)
                    per_share_cost = price + config.commission_per_share
                    estimated = int(((cash - max(config.commission_per_trade, config.minimum_commission)) / per_share_cost).to_integral_value(rounding=ROUND_FLOOR))
                    while estimated > 0:
                        fee = commission(estimated, config.commission_per_trade, config.commission_per_share, config.minimum_commission)
                        if price * estimated + fee <= cash:
                            break
                        estimated -= 1
                    if estimated < 1:
                        pending.status = "CANCELLED"
                        pending.failure_reason = "INSUFFICIENT_CASH"
                    else:
                        fee = commission(estimated, config.commission_per_trade, config.commission_per_share, config.minimum_commission)
                        notional = price * estimated
                        cash -= notional + fee
                        shares = estimated
                        state = PositionState.LONG
                        current_trade = TradeResult(
                            trade_number=len(trades) + 1, status="OPEN",
                            entry_signal_timestamp=pending.signal_timestamp,
                            entry_execution_timestamp=bar.timestamp,
                            entry_signal_type=pending.signal_type,
                            entry_raw_price=raw, entry_adjusted_price=price,
                            entry_shares=shares, entry_notional=notional, entry_fees=fee,
                        )
                        trades.append(current_trade)
                        holding_bars = [bar]
                        pending.status = "EXECUTED"
                    pending = None
                elif current_trade is not None:
                    price = adjusted_price(raw, config.slippage_bps, False)
                    fee = commission(shares, config.commission_per_trade, config.commission_per_share, config.minimum_commission)
                    notional = price * shares
                    cash += notional - fee
                    self._close_trade(current_trade, pending, bar, price, raw, notional, fee, holding_bars)
                    shares = 0
                    state = PositionState.FLAT
                    current_trade = None
                    holding_bars = []
                    pending.status = "EXECUTED"
                    pending = None

            if state == PositionState.LONG and (not holding_bars or holding_bars[-1].timestamp != bar.timestamp):
                holding_bars.append(bar)

            signal = signal_map.get(bar.timestamp)
            if signal is not None and pending is None:
                next_timestamp = selected[index + 1].timestamp if index + 1 < len(selected) else None
                if state == PositionState.FLAT and signal.signal_type == "CANDIDATE_BUY":
                    pending = PendingAction(ActionType.ENTER_LONG_PENDING, bar.timestamp, signal.signal_type, next_timestamp)
                elif state == PositionState.LONG and signal.signal_type in {"CANDIDATE_EXIT", "CANDIDATE_REDUCE"}:
                    pending = PendingAction(ActionType.EXIT_LONG_PENDING, bar.timestamp, signal.signal_type, next_timestamp)
                if pending is not None:
                    pending_rows.append(pending)

            market_value = bar.close * shares
            equity = cash + market_value
            peak = max(peak, equity)
            points.append(EquityPoint(
                timestamp=bar.timestamp, cash=cash, position_shares=shares,
                position_market_value=market_value, equity=equity, running_peak=peak,
                drawdown_amount=equity - peak, drawdown_pct=equity / peak - 1,
                signal_type=signal.signal_type if signal else None, position_state=state,
            ))

        if pending is not None:
            pending.status = "UNFILLED_END_OF_DATA"
            pending.failure_reason = "回测结束，无下一根K线可成交。"
        last = selected[-1]
        if shares and current_trade is not None and config.force_close_at_end:
            raw = last.close
            price = adjusted_price(raw, config.slippage_bps, False)
            fee = commission(shares, config.commission_per_trade, config.commission_per_share, config.minimum_commission)
            notional = price * shares
            cash += notional - fee
            forced = PendingAction(
                ActionType.EXIT_LONG_PENDING, last.timestamp, "FORCED_END_OF_BACKTEST",
                last.timestamp, status="EXECUTED",
            )
            self._close_trade(current_trade, forced, last, price, raw, notional, fee, holding_bars, forced=True)
            shares = 0
            state = PositionState.FLAT
            points[-1] = self._replace_final_point(points[-1], cash)

        ending_equity = cash + selected[-1].close * shares
        metrics = calculate_metrics(config.initial_cash, ending_equity, trades, points)
        metrics["forced_exit_count"] = sum(trade.status == "FORCED_CLOSED" for trade in trades)
        metrics["open_position"] = bool(shares)
        metrics["unrealized_pnl"] = (
            selected[-1].close * shares - (current_trade.entry_notional if current_trade else Decimal("0"))
        )
        return BacktestResult(
            status="SUCCESS", bars_processed=len(selected), signals_processed=len(selected_signals),
            ending_cash=cash, ending_equity=ending_equity, trades=trades,
            equity_points=points, pending_actions=pending_rows, metrics=metrics,
        )

    @staticmethod
    def _close_trade(trade, action, bar, price, raw, notional, fee, holding_bars, forced=False):
        trade.status = "FORCED_CLOSED" if forced else "CLOSED"
        trade.exit_signal_timestamp = action.signal_timestamp
        trade.exit_execution_timestamp = bar.timestamp
        trade.exit_signal_type = action.signal_type
        trade.exit_reason = "FORCED_END_OF_BACKTEST" if forced else action.signal_type
        trade.exit_raw_price = raw
        trade.exit_adjusted_price = price
        trade.exit_notional = notional
        trade.exit_fees = fee
        trade.gross_pnl = notional - trade.entry_notional
        trade.net_pnl = trade.gross_pnl - trade.entry_fees - fee
        trade.return_pct = trade.net_pnl / (trade.entry_notional + trade.entry_fees)
        trade.holding_bars = len(holding_bars)
        trade.holding_seconds = int((bar.timestamp - trade.entry_execution_timestamp).total_seconds())
        lows = [value.low for value in holding_bars]
        highs = [value.high for value in holding_bars]
        trade.mae_pct = min(lows) / trade.entry_adjusted_price - 1 if lows else Decimal("0")
        trade.mfe_pct = max(highs) / trade.entry_adjusted_price - 1 if highs else Decimal("0")

    @staticmethod
    def _replace_final_point(point: EquityPoint, cash: Decimal) -> EquityPoint:
        peak = max(point.running_peak, cash)
        return EquityPoint(
            timestamp=point.timestamp, cash=cash, position_shares=0,
            position_market_value=Decimal("0"), equity=cash, running_peak=peak,
            drawdown_amount=cash - peak, drawdown_pct=cash / peak - 1,
            signal_type=point.signal_type, position_state=PositionState.FLAT,
        )
