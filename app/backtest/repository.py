from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.backtest.models import BacktestBar, BacktestConfig, BacktestResult, BacktestSignal
from app.database.models import (
    BacktestEquityPoint, BacktestPendingAction, BacktestRun, BacktestTrade,
    CandidateSignal, MarketBar,
)


class BacktestRepository:
    def __init__(self, db: Session):
        self.db = db

    def load_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[BacktestBar]:
        normalized = symbol if symbol.startswith("US.") else "US." + symbol
        rows = self.db.scalars(select(MarketBar).where(
            MarketBar.symbol == normalized, MarketBar.interval == timeframe,
            MarketBar.timestamp_utc >= start, MarketBar.timestamp_utc <= end,
            MarketBar.adjustment_type == "FORWARD", MarketBar.data_source == "MOOMOO",
            MarketBar.is_blank.is_(False),
        ).order_by(MarketBar.timestamp_utc))
        return [
            BacktestBar(
                timestamp=self.aware(row.timestamp_utc), open=Decimal(row.open),
                high=Decimal(row.high), low=Decimal(row.low), close=Decimal(row.close),
                volume=row.volume,
            )
            for row in rows
        ]

    def load_signals(self, config: BacktestConfig) -> List[BacktestSignal]:
        rows = self.db.scalars(select(CandidateSignal).where(
            CandidateSignal.symbol == config.symbol.replace("US.", ""),
            CandidateSignal.timeframe == config.timeframe,
            CandidateSignal.strategy_name == "pullback_restrength",
            CandidateSignal.strategy_version == "1.0.0",
            CandidateSignal.parameters_hash == config.parameters_hash,
            CandidateSignal.bar_timestamp >= config.start_time,
            CandidateSignal.bar_timestamp <= config.end_time,
        ).order_by(CandidateSignal.bar_timestamp))
        return [
            BacktestSignal(self.aware(row.bar_timestamp), row.signal_type, row.parameters_hash)
            for row in rows
        ]

    def duplicate_run_ids(self, configuration_hash: str) -> List[int]:
        return list(self.db.scalars(select(BacktestRun.id).where(
            BacktestRun.configuration_hash == configuration_hash,
        ).order_by(desc(BacktestRun.id))))

    def create_run(self, config: BacktestConfig, configuration_hash: str, benchmark_symbol: Optional[str]) -> BacktestRun:
        run = BacktestRun(
            run_name="%s %s %s" % (config.symbol, config.timeframe, config.run_mode.value),
            run_mode=config.run_mode.value, symbol=config.symbol.replace("US.", ""), market="US",
            timeframe=config.timeframe, strategy_name="pullback_restrength",
            strategy_version="1.0.0", parameters_hash=config.parameters_hash,
            configuration_hash=configuration_hash, start_time=config.start_time,
            end_time=config.end_time, initial_cash=config.initial_cash,
            commission_per_trade=config.commission_per_trade,
            commission_per_share=config.commission_per_share,
            minimum_commission=config.minimum_commission, slippage_bps=config.slippage_bps,
            force_close_at_end=config.force_close_at_end, benchmark_symbol=benchmark_symbol,
            status="RUNNING", started_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        self.db.commit()
        return run

    def persist_result(self, run: BacktestRun, result: BacktestResult) -> None:
        run.status = result.status
        run.bars_processed = result.bars_processed
        run.signals_processed = result.signals_processed
        run.ending_cash = result.ending_cash
        run.ending_equity = result.ending_equity
        run.entries_count = len(result.trades)
        run.exits_count = sum(trade.status != "OPEN" for trade in result.trades)
        run.error_summary = {"errors": result.errors}
        run.finished_at = datetime.now(timezone.utc)
        for key, value in result.metrics.items():
            if hasattr(run, key):
                setattr(run, key, value)
        for trade in result.trades:
            self.db.add(BacktestTrade(
                backtest_run_id=run.id, symbol=run.symbol, timeframe=run.timeframe,
                **trade.__dict__,
            ))
        self.db.add_all([
            BacktestEquityPoint(
                backtest_run_id=run.id, timestamp=point.timestamp, cash=point.cash,
                position_shares=point.position_shares,
                position_market_value=point.position_market_value, equity=point.equity,
                running_peak=point.running_peak, drawdown_amount=point.drawdown_amount,
                drawdown_pct=point.drawdown_pct, signal_type=point.signal_type,
                position_state=point.position_state.value,
            )
            for point in result.equity_points
        ])
        self.db.add_all([
            BacktestPendingAction(
                backtest_run_id=run.id, symbol=run.symbol, timeframe=run.timeframe,
                action_type=action.action_type.value,
                signal_timestamp=action.signal_timestamp, signal_type=action.signal_type,
                scheduled_execution_timestamp=action.scheduled_execution_timestamp,
                status=action.status, failure_reason=action.failure_reason,
            )
            for action in result.pending_actions
        ])
        self.db.add(run)
        self.db.commit()

    @staticmethod
    def aware(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
