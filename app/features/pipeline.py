import math
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional

import pandas as pd

from app.core.enums import (
    BarInterval, FeatureJobType, FeatureQualityStatus, FeatureValueType,
)
from app.database.models import FeatureCalculationJob
from app.features.calculator import FeatureCalculator
from app.features.models import FeatureDefinition, FeatureValue
from app.features.quality import FeatureQualityService
from app.features.registry import FeatureRegistry, parameters_hash
from app.features.repository import FeatureRepository
from app.features.validation import validate_input_bars


class FeatureCalculationService:
    def __init__(self, repository: FeatureRepository, registry: Optional[FeatureRegistry] = None, calculator: Optional[FeatureCalculator] = None):
        self.repository = repository
        self.registry = registry or FeatureRegistry.defaults()
        self.calculator = calculator or FeatureCalculator()
        self.quality = FeatureQualityService()

    def calculate_symbol(
        self,
        symbol: str,
        interval: BarInterval,
        feature_names: Optional[Iterable[str]] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        job_type: FeatureJobType = FeatureJobType.FULL,
        realtime: bool = False,
    ) -> FeatureCalculationJob:
        names = list(feature_names or [item.feature_name for item in self.registry.list()])
        definitions = [self.registry.get(name) for name in names if interval.value in self.registry.get(name).supported_intervals]
        job = FeatureCalculationJob(
            job_id=str(uuid.uuid4()), job_type=job_type.value, symbols_json=[symbol],
            intervals_json=[interval.value], feature_names_json=names, start_time=start,
            end_time=end, status="RUNNING", started_at=datetime.now(timezone.utc),
        )
        self.repository.db.add(job)
        self.repository.db.commit()
        began = time.monotonic()
        try:
            warmup = max([item.required_bars for item in definitions] or [1])
            effective_start = None
            output_start = start
            if job_type == FeatureJobType.INCREMENTAL and definitions:
                latest_values = [
                    self.repository.latest_timestamp(
                        symbol, interval.value, definition.feature_name,
                        "MOOMOO_REALTIME" if realtime else "MOOMOO",
                    )
                    for definition in definitions
                ]
                if all(latest_values):
                    output_start = min(latest_values)
                    effective_start = self._warmup_start(
                        output_start, interval, warmup,
                    )
            bars = self.repository.load_bars(symbol, interval.value, effective_start, end, realtime)
            job.input_rows = len(bars)
            if bars.empty:
                job.status = "SKIPPED"
                job.error_code = "EMPTY_INPUT"
                job.error_message = "没有可用于特征计算的K线"
                return self._finish(job, began)
            input_issues = validate_input_bars(bars)
            if input_issues:
                for issue in input_issues:
                    self.repository.record_issue(
                        symbol, interval.value, "*", issue,
                        "输入K线未通过特征计算前校验", severity="ERROR",
                    )
                job.status = "FAILED"
                job.error_code = "INPUT_INVALID"
                job.error_message = "输入K线未通过校验：" + "、".join(input_issues)
                return self._finish(job, began)
            references = self._load_references(interval, bars.index.min().to_pydatetime(), bars.index.max().to_pydatetime(), realtime)
            calculated = self.calculator.calculate(bars, interval.value, references)
            failed = 0
            for definition in definitions:
                try:
                    series = calculated.get(definition.feature_name)
                    if series is None:
                        raise KeyError("计算器未返回该特征")
                    if definition.requires_reference_symbol and definition.reference_symbol not in references:
                        self.repository.record_issue(
                            symbol, interval.value, definition.feature_name,
                            "REFERENCE_DATA_MISSING",
                            "参考标的%s在相同周期没有可精确对齐的数据" % definition.reference_symbol,
                        )
                    for issue in self.quality.validate_output(definition.feature_name, series):
                        self.repository.record_issue(
                            symbol, interval.value, definition.feature_name, issue,
                            "特征输出未通过质量范围校验", severity="ERROR",
                        )
                    values = self._to_values(symbol, interval, bars, series, definition, realtime, output_start, end)
                    written, updated = self.repository.upsert_values(values)
                    job.output_rows += len(values)
                    job.inserted_rows += written
                    job.updated_rows += updated
                except Exception as exc:
                    failed += 1
                    self.repository.db.rollback()
                    self.repository.record_issue(symbol, interval.value, definition.feature_name, "CALCULATION_ERROR", type(exc).__name__ + "：" + str(exc), severity="ERROR")
            job.failed_features = failed
            job.status = "SUCCESS" if failed == 0 else "PARTIAL"
            job.metadata_json = {
                "duration_seconds": round(time.monotonic() - began, 6),
                "rows_per_second": round(job.output_rows / max(time.monotonic() - began, 0.000001), 2),
                "realtime": realtime,
            }
        except Exception as exc:
            self.repository.db.rollback()
            job.status = "FAILED"
            job.error_code = "CALCULATION_ERROR"
            job.error_message = type(exc).__name__ + "：" + str(exc)
        return self._finish(job, began)

    def calculate_features(self, *args, **kwargs):
        return self.calculate_symbol(*args, **kwargs)

    def incremental_update(self, symbol: str, interval: BarInterval, feature_names=None, realtime: bool = False):
        return self.calculate_symbol(symbol, interval, feature_names, job_type=FeatureJobType.INCREMENTAL, realtime=realtime)

    @staticmethod
    def _warmup_start(latest: datetime, interval: BarInterval, bars: int) -> datetime:
        """Bound incremental reads while retaining enough input for rolling features."""
        unit = {
            BarInterval.MIN_1: timedelta(minutes=1),
            BarInterval.MIN_5: timedelta(minutes=5),
            BarInterval.MIN_15: timedelta(minutes=15),
            BarInterval.MIN_30: timedelta(minutes=30),
            BarInterval.HOUR_1: timedelta(hours=1),
            # Calendar gaps require a wider window than `bars` trading days.
            BarInterval.DAY_1: timedelta(days=3),
        }[interval]
        return latest - unit * max(bars + 5, 10)

    def repair_range(self, symbol: str, interval: BarInterval, start: datetime, end: datetime, feature_names=None):
        return self.calculate_symbol(symbol, interval, feature_names, start, end, FeatureJobType.REPAIR)

    def calculate_all(self, symbols: Iterable[str], intervals: Iterable[BarInterval], feature_names=None) -> List[FeatureCalculationJob]:
        jobs = []
        for symbol in symbols:
            for interval in intervals:
                jobs.append(self.calculate_symbol(symbol, interval, feature_names))
        return jobs

    def calculate_realtime_closed(self, symbol: str, feature_names=None):
        return self.incremental_update(symbol, BarInterval.MIN_1, feature_names, realtime=True)

    def _load_references(self, interval: BarInterval, start: datetime, end: datetime, realtime: bool) -> Dict[str, pd.DataFrame]:
        values = {}
        for symbol in ("US.QQQ", "US.SOXX"):
            frame = self.repository.load_bars(symbol, interval.value, start, end, realtime)
            if not frame.empty:
                values[symbol] = frame
        return values

    def _to_values(self, symbol: str, interval: BarInterval, bars: pd.DataFrame, series: pd.Series, definition: FeatureDefinition, realtime: bool, requested_start: Optional[datetime], requested_end: Optional[datetime]) -> List[FeatureValue]:
        output = []
        param_hash = parameters_hash(definition.default_parameters)
        for position, (timestamp, raw) in enumerate(series.items()):
            moment = timestamp.to_pydatetime()
            if requested_start and moment < requested_start:
                continue
            if requested_end and moment > requested_end:
                continue
            quality = FeatureQualityStatus.VALID
            message = None
            value = raw
            if position < definition.required_bars - 1:
                quality, message, value = FeatureQualityStatus.WARMUP, "预热K线不足", None
            elif raw is None or (not isinstance(raw, str) and pd.isna(raw)):
                quality, message, value = FeatureQualityStatus.MISSING, "输入缺失或无法计算", None
            elif definition.value_type == FeatureValueType.DECIMAL:
                try:
                    numeric = float(raw)
                    if not math.isfinite(numeric):
                        raise ValueError("非有限值")
                    if definition.feature_name == "rsi_14" and not 0 <= numeric <= 100:
                        raise ValueError("RSI超出0至100")
                    if definition.feature_name in ("atr_14", "volume_ratio_20") and numeric < 0:
                        raise ValueError("输出不应为负数")
                    value = Decimal(str(numeric)).quantize(Decimal("0.000000000001"))
                except (ValueError, InvalidOperation, OverflowError):
                    quality, message, value = FeatureQualityStatus.INVALID, "输出不是有限数值", None
            elif definition.value_type == FeatureValueType.TEXT:
                value = str(raw)
            output.append(FeatureValue(
                symbol=symbol, interval=interval, timestamp_utc=moment,
                feature_name=definition.feature_name, feature_version=definition.version,
                parameters_hash=param_hash, value=value, value_type=definition.value_type,
                quality_status=quality, quality_message=message,
                source_bar_timestamp=moment,
                data_source="MOOMOO_REALTIME" if realtime else "MOOMOO",
            ))
        return output

    def _finish(self, job: FeatureCalculationJob, began: float) -> FeatureCalculationJob:
        job.finished_at = datetime.now(timezone.utc)
        if not job.metadata_json:
            job.metadata_json = {"duration_seconds": round(time.monotonic() - began, 6)}
        self.repository.db.add(job)
        self.repository.db.commit()
        return job

    @staticmethod
    def _lookback_delta(interval: BarInterval, bars: int) -> timedelta:
        minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1d": 1440}[interval.value]
        return timedelta(minutes=minutes * bars * 3)
