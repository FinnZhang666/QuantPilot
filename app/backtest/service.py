import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest.benchmark import buy_and_hold
from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig, RunMode
from app.backtest.repository import BacktestRepository
from app.database.models import StrategyParameterSet, WatchlistItem


class BacktestService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = BacktestRepository(db)

    def run(
        self, symbol: str, timeframe: str, start_time: datetime, end_time: datetime,
        run_mode: str = "SIGNAL_REPLAY", parameters_hash: Optional[str] = None,
        initial_cash: Decimal = Decimal("100000"), commission_per_trade: Decimal = Decimal("0"),
        commission_per_share: Decimal = Decimal("0"), minimum_commission: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"), force_close_at_end: bool = True,
    ) -> Dict[str, object]:
        symbol = symbol.upper().replace("US.", "")
        item = self.db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol))
        if not item:
            raise ValueError("Ticker不存在于观察池中。")
        parameter = self.db.scalar(select(StrategyParameterSet).where(
            StrategyParameterSet.watchlist_item_id == item.id,
            StrategyParameterSet.enabled.is_(True),
        ))
        selected_hash = parameters_hash or (parameter.parameters_hash if parameter else None)
        if not selected_hash:
            raise ValueError("找不到启用的策略参数。")
        config = BacktestConfig(
            symbol=symbol, timeframe=timeframe, start_time=start_time, end_time=end_time,
            parameters_hash=selected_hash, initial_cash=initial_cash,
            commission_per_trade=commission_per_trade,
            commission_per_share=commission_per_share,
            minimum_commission=minimum_commission, slippage_bps=slippage_bps,
            force_close_at_end=force_close_at_end, run_mode=RunMode(run_mode.upper()),
        )
        configuration_hash = self.configuration_hash(config)
        existing = self.repository.duplicate_run_ids(configuration_hash)
        benchmark_symbol = item.benchmark_symbol or "QQQ"
        run = self.repository.create_run(config, configuration_hash, benchmark_symbol)
        bars = self.repository.load_bars(symbol, timeframe, start_time, end_time)
        if config.run_mode == RunMode.SIGNAL_REPLAY:
            signals = self.repository.load_signals(config)
        else:
            signals = self._recompute_signals(item, parameter, timeframe, bars)
        result = BacktestEngine().run(config, bars, signals)
        symbol_hold = buy_and_hold(initial_cash, bars)
        benchmark_bars = self.repository.load_bars(benchmark_symbol, timeframe, start_time, end_time)
        benchmark = buy_and_hold(initial_cash, benchmark_bars)
        if (
            benchmark["status"] == "AVAILABLE" and benchmark_bars and
            (benchmark_bars[0].timestamp > start_time or benchmark_bars[-1].timestamp < end_time)
        ):
            benchmark["status"] = "PARTIAL_COVERAGE"
        if benchmark["status"] == "UNAVAILABLE" and benchmark_symbol != "QQQ":
            benchmark_symbol = "QQQ"
            benchmark_bars = self.repository.load_bars("QQQ", timeframe, start_time, end_time)
            benchmark = buy_and_hold(initial_cash, benchmark_bars)
            if benchmark["status"] == "AVAILABLE":
                benchmark["status"] = "FALLBACK"
        result.metrics["symbol_buy_hold_return_pct"] = symbol_hold["return_pct"]
        result.metrics["benchmark_return_pct"] = benchmark["return_pct"]
        if result.metrics.get("total_return_pct") is not None and symbol_hold["return_pct"] is not None:
            result.metrics["excess_return_vs_symbol_pct"] = result.metrics["total_return_pct"] - symbol_hold["return_pct"]
        if result.metrics.get("total_return_pct") is not None and benchmark["return_pct"] is not None:
            result.metrics["excess_return_vs_benchmark_pct"] = result.metrics["total_return_pct"] - benchmark["return_pct"]
        run.benchmark_symbol = benchmark_symbol
        run.benchmark_status = benchmark["status"]
        self.repository.persist_result(run, result)
        return {
            "run_id": run.id, "status": result.status,
            "duplicate_configuration": bool(existing), "existing_run_ids": existing,
            "bars_processed": result.bars_processed, "signals_processed": result.signals_processed,
            "trades": len(result.trades), "metrics": result.metrics,
            "benchmark_symbol": benchmark_symbol, "benchmark_status": benchmark["status"],
            "errors": result.errors,
        }

    def _recompute_signals(self, item, parameter, timeframe, bars):
        if parameter is None:
            raise ValueError("STRATEGY_RECOMPUTE需要启用的策略参数。")
        from app.strategy.models import StrategyInput
        from app.strategy.service import StrategyRunner
        runner = StrategyRunner(self.db)
        output = []
        for bar in bars:
            resolved = runner.resolver.resolve(
                item.symbol, timeframe, bar.timestamp,
                item.benchmark_symbol, False,
            )
            strategy_input = StrategyInput(
                symbol=item.symbol, market=item.market, timeframe=timeframe,
                bar_timestamp=bar.timestamp, enabled=item.enabled, role=item.role,
                validation_status=item.validation_status,
                benchmark_symbol=item.benchmark_symbol or "QQQ",
                parameters=parameter.parameters_json, parameters_hash=parameter.parameters_hash,
                features=resolved["values"], feature_statuses=resolved["statuses"],
                feature_refs=resolved["refs"],
            )
            evaluation = runner.strategy.evaluate(strategy_input)
            from app.backtest.models import BacktestSignal
            output.append(BacktestSignal(bar.timestamp, evaluation.signal_type, parameter.parameters_hash))
        return output

    @staticmethod
    def configuration_hash(config: BacktestConfig) -> str:
        payload = asdict(config)
        payload["run_mode"] = config.run_mode.value
        normalized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
