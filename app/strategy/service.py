import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.models import WatchlistItem
from app.features.pipeline import FeatureCalculationService
from app.features.repository import FeatureRepository
from app.strategy.constants import RUN_TYPES
from app.strategy.dependencies import FeatureDependencyResolver
from app.strategy.disk import DiskSpaceGuard
from app.strategy.models import StrategyInput
from app.strategy.repository import StrategyRepository
from app.strategy.strategies.pullback_restrength import PullbackRestrengthStrategy


class StrategyRunner:
    def __init__(
        self, db: Session, settings: Optional[Settings] = None,
        feature_service: Optional[FeatureCalculationService] = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.repository = StrategyRepository(db, self.settings.strategy_read_chunk_size)
        if feature_service is None:
            feature_service = FeatureCalculationService(FeatureRepository(
                db, self.settings.feature_write_batch_size,
                self.settings.feature_read_chunk_size,
            ))
        self.resolver = FeatureDependencyResolver(self.repository, feature_service)
        self.strategy = PullbackRestrengthStrategy()
        self.disk = DiskSpaceGuard(
            self.settings.moomoo_warn_free_disk_gb,
            self.settings.moomoo_min_free_disk_gb,
        )
        self._benchmark_cache: Dict[str, object] = {}

    def run(
        self, symbols: Iterable[str], timeframes: Iterable[str],
        mode: str = "INCREMENTAL", start: Optional[datetime] = None,
        end: Optional[datetime] = None, auto_calculate_features: Optional[bool] = None,
        dry_run: bool = False, confirm_large_run: bool = False,
    ) -> Dict[str, object]:
        began = time.monotonic()
        mode = mode.upper()
        if mode not in RUN_TYPES:
            raise ValueError("运行模式无效。")
        symbols = [value.strip().upper().replace("US.", "") for value in symbols]
        timeframes = list(dict.fromkeys(timeframes))
        if mode in ("FULL", "RANGE") and (not start or not end):
            raise ValueError("FULL和RANGE模式必须指定开始及结束时间。")
        if start and end and start >= end:
            raise ValueError("时间范围无效。")
        items = self._validate_items(symbols, timeframes)
        estimated = self.repository.estimate_bars(symbols, timeframes, start, end)
        span_days = (end - start).total_seconds() / 86400 if start and end else 0
        large = (
            len(symbols) > 5 or len(timeframes) > 3 or span_days > 90 or
            estimated > self.settings.strategy_max_estimated_bars
        )
        if large and not confirm_large_run:
            raise ValueError("该任务预计处理数据量较大，请确认后重新提交。")
        auto = (
            self.settings.moomoo_strategy_auto_calculate_features
            if auto_calculate_features is None else auto_calculate_features
        )
        disk = self.disk.enforce(large, auto)
        preview = {
            "symbols": symbols, "symbol_count": len(symbols),
            "timeframes": timeframes, "timeframe_count": len(timeframes),
            "start_time": start, "end_time": end, "estimated_bars": estimated,
            "free_disk_gb": disk.free_gb, "disk_warning": disk.warning,
            "large_task": large, "dry_run": dry_run,
        }
        if dry_run:
            required, optional, _ = self.resolver.dependency_names("QQQ")
            preview["required_features"] = required
            preview["optional_features"] = optional
            preview["estimated_missing_features"] = self._estimate_missing_features(
                items, timeframes, required + optional,
            )
            return preview
        run = self.repository.create_run(mode, symbols, timeframes, disk.free_gb)
        errors: Dict[str, str] = {}
        for item in items:
            for timeframe in timeframes:
                key = item.symbol + "/" + timeframe
                try:
                    self._run_item(run, item, timeframe, mode, start, end, auto)
                except Exception as exc:
                    self.db.rollback()
                    run.errors_count += 1
                    errors[key] = type(exc).__name__ + "：" + str(exc)
        if errors and run.signals_written:
            status = "PARTIAL_SUCCESS"
        elif errors:
            status = "FAILED"
        else:
            status = "SUCCESS"
        self.repository.finish_run(run, status, began, errors)
        return {
            "run_id": run.run_id, "status": run.status,
            "bars_evaluated": run.bars_evaluated,
            "signals_written": run.signals_written,
            "signals_skipped": run.signals_skipped,
            "errors_count": run.errors_count,
            "elapsed_seconds": run.elapsed_seconds,
            "free_disk_gb": run.free_disk_gb,
            "errors": errors,
        }

    def _run_item(
        self, run, item: WatchlistItem, timeframe: str, mode: str,
        start: Optional[datetime], end: Optional[datetime], auto: bool,
    ) -> None:
        parameters = self.repository.get_parameter_set(item.id)
        if not parameters:
            raise RuntimeError("策略参数不存在或已停用")
        effective_start = start
        realtime = mode == "REALTIME"
        if mode == "INCREMENTAL":
            latest = self.repository.latest_signal_timestamp(
                item.symbol, timeframe, parameters.parameters_hash,
            )
            if latest:
                effective_start = latest + timedelta(microseconds=1)
            elif effective_start is None:
                timestamps = self.repository.bar_timestamps(item.symbol, timeframe, None, end)
                effective_start = timestamps[-1] if timestamps else None
        timestamps = self.repository.bar_timestamps(
            item.symbol, timeframe, effective_start, end, realtime,
        )
        for offset in range(0, len(timestamps), self.settings.strategy_read_chunk_size):
            pending = []
            for timestamp in timestamps[offset:offset + self.settings.strategy_read_chunk_size]:
                resolved = self.resolver.resolve(
                    item.symbol, timeframe, timestamp, item.benchmark_symbol, auto,
                    realtime=realtime,
                )
                strategy_input = StrategyInput(
                    symbol=item.symbol, market=item.market, timeframe=timeframe,
                    bar_timestamp=self._aware(timestamp), enabled=item.enabled, role=item.role,
                    validation_status=item.validation_status,
                    benchmark_symbol=item.benchmark_symbol or "QQQ",
                    parameters=parameters.parameters_json,
                    parameters_hash=parameters.parameters_hash,
                    features=resolved["values"], feature_statuses=resolved["statuses"],
                    feature_refs=resolved["refs"],
                )
                evaluation = self.strategy.evaluate(strategy_input)
                pending.append((
                    item, timeframe, self._aware(timestamp),
                    parameters.parameters_hash, evaluation,
                ))
                run.bars_evaluated += 1
            run.signals_written += self.repository.upsert_signals(pending)
        if not timestamps:
            run.signals_skipped += 1
        self.db.add(run)
        self.db.commit()

    def _validate_items(self, symbols: List[str], timeframes: List[str]) -> List[WatchlistItem]:
        rows = list(self.db.scalars(select(WatchlistItem).where(
            WatchlistItem.symbol.in_(symbols),
        )))
        found = {row.symbol: row for row in rows}
        missing = [symbol for symbol in symbols if symbol not in found]
        if missing:
            raise KeyError("Ticker不存在于观察池中：" + "、".join(missing))
        disabled = [row.symbol for row in rows if not row.enabled]
        if disabled:
            raise ValueError("Ticker当前已停用：" + "、".join(disabled))
        for row in rows:
            for timeframe in timeframes:
                if not self.repository.timeframe_enabled(row.id, timeframe):
                    raise ValueError("%s未启用周期%s。" % (row.symbol, timeframe))
        return [found[symbol] for symbol in symbols]

    def _estimate_missing_features(
        self, items: List[WatchlistItem], timeframes: List[str], names: List[str],
    ) -> int:
        missing = 0
        for item in items:
            for timeframe in timeframes:
                timestamp = self.repository.latest_bar_timestamp(item.symbol, timeframe)
                if not timestamp:
                    missing += len(names)
                    continue
                rows = self.repository.feature_values(
                    item.symbol, timeframe, timestamp, names,
                )
                missing += len(set(names) - set(rows))
        return missing

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
