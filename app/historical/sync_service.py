import uuid
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.enums import AdjustmentType, BarInterval, HistoryErrorCode, HistoryJobStatus
from app.database.models import (
    HistoryDataIssue,
    HistorySyncJob,
    Instrument,
    MarketBar,
)
from app.historical.base import HistoricalDataProvider
from app.historical.models import HistoryFetchResult, MarketBarData


STATUS_TEXT = {
    HistoryJobStatus.PENDING.value: "等待同步",
    HistoryJobStatus.RUNNING.value: "同步中",
    HistoryJobStatus.SUCCESS.value: "同步成功",
    HistoryJobStatus.PARTIAL.value: "部分成功",
    HistoryJobStatus.FAILED.value: "同步失败",
    HistoryJobStatus.SKIPPED.value: "已跳过",
}
logger = logging.getLogger(__name__)


class HistoricalDataSyncService:
    def __init__(self, db: Session, provider: HistoricalDataProvider):
        self.db = db
        self.provider = provider

    @staticmethod
    def overlap_start(interval: BarInterval, latest: datetime) -> datetime:
        if interval == BarInterval.DAY_1:
            return latest - timedelta(days=8)
        minutes = {
            BarInterval.MIN_1: 1,
            BarInterval.MIN_5: 5,
            BarInterval.MIN_15: 15,
            BarInterval.MIN_30: 30,
            BarInterval.HOUR_1: 60,
        }[interval]
        return latest - timedelta(minutes=minutes * 20)

    def incremental_start(
        self, symbol: str, interval: BarInterval, fallback: datetime
    ) -> datetime:
        latest = self.db.scalar(
            select(func.max(MarketBar.timestamp_utc)).where(
                MarketBar.symbol == symbol, MarketBar.interval == interval.value
            )
        )
        if latest is not None and latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return self.overlap_start(interval, latest) if latest else fallback

    def _job(
        self,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
        adjustment: AdjustmentType,
    ) -> HistorySyncJob:
        job = HistorySyncJob(
            job_id=str(uuid.uuid4()),
            symbol=symbol,
            interval=interval.value,
            start_time=start,
            end_time=end,
            adjustment_type=adjustment.value,
            status=HistoryJobStatus.PENDING.value,
        )
        self.db.add(job)
        self.db.commit()
        return job

    def sync_symbol(
        self,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
        adjustment: AdjustmentType = AdjustmentType.FORWARD,
        incremental: bool = False,
        repair: bool = False,
    ) -> HistorySyncJob:
        instrument = self.db.scalar(select(Instrument).where(Instrument.symbol == symbol))
        job = self._job(symbol, interval, start, end, adjustment)
        if instrument is None or not instrument.is_supported:
            job.status = HistoryJobStatus.SKIPPED.value
            job.error_code = HistoryErrorCode.UNSUPPORTED_SECURITY.value
            job.error_message = "标的未验证或当前不支持"
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            return job
        if incremental:
            start = self.incremental_start(symbol, interval, start)
            job.start_time = start
        job.status = HistoryJobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        result = self.provider.fetch_bars(symbol, interval, start, end, adjustment)
        job.pages_requested = result.pages_requested
        job.rows_received = len(result.bars)
        if not result.success and not result.bars:
            job.status = HistoryJobStatus.FAILED.value
            job.error_code = result.error_code.value if result.error_code else None
            job.error_message = result.error_message_zh
        else:
            try:
                inserted, updated, skipped = self._upsert(instrument, result.bars)
            except Exception as exc:
                job_id = job.id
                self.db.rollback()
                job = self.db.get(HistorySyncJob, job_id)
                job.status = HistoryJobStatus.FAILED.value
                job.error_code = HistoryErrorCode.DATABASE_ERROR.value
                job.error_message = "数据库批量写入失败：" + type(exc).__name__
                job.finished_at = datetime.now(timezone.utc)
                self.db.commit()
                return job
            job.rows_inserted = inserted
            job.rows_updated = updated
            job.rows_skipped = skipped
            job.status = (
                HistoryJobStatus.PARTIAL.value
                if result.error_code
                else HistoryJobStatus.SUCCESS.value
            )
            job.error_code = result.error_code.value if result.error_code else None
            job.error_message = result.error_message_zh or None
        job.finished_at = datetime.now(timezone.utc)
        job.metadata_json = {"warnings": result.warnings, "repair": repair}
        self.db.commit()
        duration = (
            (job.finished_at - job.started_at).total_seconds()
            if job.started_at and job.finished_at
            else 0
        )
        logger.info(
            "历史行情同步完成",
            extra={
                "component": "historical_data",
                "event": "history_sync_completed",
                "context": {
                    "job_id": job.job_id,
                    "symbol": job.symbol,
                    "interval": job.interval,
                    "start_time": job.start_time,
                    "end_time": job.end_time,
                    "pages": job.pages_requested,
                    "rows_received": job.rows_received,
                    "rows_inserted": job.rows_inserted,
                    "rows_updated": job.rows_updated,
                    "rows_skipped": job.rows_skipped,
                    "duration": duration,
                    "status": job.status,
                    "error_code": job.error_code,
                },
            },
        )
        return job

    def _upsert(
        self, instrument: Instrument, bars: List[MarketBarData]
    ) -> Tuple[int, int, int]:
        valid: List[MarketBarData] = []
        skipped = 0
        for bar in bars:
            errors = bar.validation_errors()
            if errors:
                skipped += 1
                self.db.add(
                    HistoryDataIssue(
                        symbol=bar.symbol,
                        interval=bar.interval.value,
                        timestamp_utc=bar.timestamp_utc,
                        issue_type=(
                            "NEGATIVE_VOLUME"
                            if any("成交量" in item for item in errors)
                            else "INVALID_OHLC"
                        ),
                        severity="ERROR",
                        message="；".join(errors),
                    )
                )
            else:
                valid.append(bar)
        if not valid:
            self.db.commit()
            return 0, 0, skipped
        times = [bar.timestamp_utc for bar in valid]
        batch_size = 500
        existing = set()
        for index in range(0, len(times), batch_size):
            existing.update(
                self.db.scalars(
                    select(MarketBar.timestamp_utc).where(
                        MarketBar.symbol == valid[0].symbol,
                        MarketBar.interval == valid[0].interval.value,
                        MarketBar.adjustment_type == valid[0].adjustment_type.value,
                        MarketBar.data_source == valid[0].data_source,
                        MarketBar.timestamp_utc.in_(times[index:index + batch_size]),
                    )
                )
            )
        rows = [
            {
                "instrument_id": instrument.id,
                "symbol": bar.symbol,
                "interval": bar.interval.value,
                "timestamp_utc": bar.timestamp_utc,
                "timestamp_market": bar.timestamp_market,
                "trading_date": bar.trading_date.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "turnover": bar.turnover,
                "change_rate": bar.change_rate,
                "last_close": bar.last_close,
                "is_blank": bar.is_blank,
                "market_session": bar.market_session.value,
                "adjustment_type": bar.adjustment_type.value,
                "data_source": bar.data_source,
            }
            for bar in valid
        ]
        for index in range(0, len(rows), batch_size):
            statement = sqlite_insert(MarketBar).values(rows[index:index + batch_size])
            statement = statement.on_conflict_do_update(
                index_elements=[
                    "symbol",
                    "interval",
                    "timestamp_utc",
                    "adjustment_type",
                    "data_source",
                ],
                set_={
                    "open": statement.excluded.open,
                    "high": statement.excluded.high,
                    "low": statement.excluded.low,
                    "close": statement.excluded.close,
                    "volume": statement.excluded.volume,
                    "turnover": statement.excluded.turnover,
                    "change_rate": statement.excluded.change_rate,
                    "last_close": statement.excluded.last_close,
                    "is_blank": statement.excluded.is_blank,
                    "market_session": statement.excluded.market_session,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            self.db.execute(statement)
        self.db.commit()
        updated = len(existing)
        return len(valid) - updated, updated, skipped

    def sync_all(
        self,
        symbols: Iterable[str],
        intervals: Iterable[BarInterval],
        start: datetime,
        end: datetime,
        adjustment: AdjustmentType = AdjustmentType.FORWARD,
    ) -> List[HistorySyncJob]:
        jobs = []
        for symbol in symbols:
            for interval in intervals:
                try:
                    jobs.append(
                        self.sync_symbol(symbol, interval, start, end, adjustment)
                    )
                except Exception as exc:
                    job = self._job(symbol, interval, start, end, adjustment)
                    job.status = HistoryJobStatus.FAILED.value
                    job.error_code = HistoryErrorCode.UNKNOWN_ERROR.value
                    job.error_message = "同步异常：" + type(exc).__name__
                    job.finished_at = datetime.now(timezone.utc)
                    self.db.commit()
                    jobs.append(job)
        return jobs

    def repair_range(self, *args, **kwargs) -> HistorySyncJob:
        kwargs["repair"] = True
        return self.sync_symbol(*args, **kwargs)
