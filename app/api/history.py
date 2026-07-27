from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import AdjustmentType, BarInterval
from app.database.models import HistoryDataIssue, HistorySyncJob, Instrument, MarketBar
from app.database.session import get_db
from app.historical.factory import build_history_provider
from app.historical.sync_service import HistoricalDataSyncService, STATUS_TEXT

router = APIRouter(tags=["历史行情"])
ABSOLUTE_BAR_LIMIT = 5000


class HistorySyncRequest(BaseModel):
    symbols: List[str] = Field(min_length=1, max_length=20)
    intervals: List[BarInterval] = Field(min_length=1, max_length=6)
    start: datetime
    end: datetime
    adjustment_type: AdjustmentType = AdjustmentType.FORWARD
    incremental: bool = False
    repair: bool = False


def _dt(value: datetime, timezone_name: str) -> str:
    source = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return source.astimezone(ZoneInfo(timezone_name)).isoformat()


@router.get("/instruments")
def instruments(
    active: Optional[bool] = None,
    supported: Optional[bool] = None,
    market: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = select(Instrument)
    if active is not None:
        query = query.where(Instrument.is_active == active)
    if supported is not None:
        query = query.where(Instrument.is_supported == supported)
    if market:
        query = query.where(Instrument.market == market.upper())
    if search:
        term = "%" + search.upper() + "%"
        query = query.where(
            or_(Instrument.symbol.ilike(term), Instrument.alias.ilike(term), Instrument.display_name.ilike(term))
        )
    rows = db.scalars(query.order_by(Instrument.symbol).offset((page - 1) * page_size).limit(page_size))
    return [
        {
            "symbol": row.symbol,
            "alias": row.alias,
            "display_name": row.display_name,
            "market": row.market,
            "supported": row.is_supported,
            "support_status": row.support_status,
            "support_message": row.support_message,
        }
        for row in rows
    ]


@router.get("/history/bars")
def history_bars(
    symbol: str,
    interval: BarInterval,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(1000, ge=1, le=ABSOLUTE_BAR_LIMIT),
    adjustment_type: AdjustmentType = AdjustmentType.FORWARD,
    timezone_name: str = Query("UTC", alias="timezone"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        ZoneInfo(timezone_name)
    except Exception:
        raise HTTPException(422, "时区名称无效，请使用UTC、America/New_York或Asia/Shanghai。")
    query = select(MarketBar).where(
        MarketBar.symbol == symbol.upper(),
        MarketBar.interval == interval.value,
        MarketBar.adjustment_type == adjustment_type.value,
    )
    if start:
        query = query.where(MarketBar.timestamp_utc >= start)
    if end:
        query = query.where(MarketBar.timestamp_utc <= end)
    rows = db.scalars(query.order_by(MarketBar.timestamp_utc).offset(offset).limit(limit))
    return [
        {
            "symbol": row.symbol,
            "interval": row.interval,
            "timestamp_utc": _dt(row.timestamp_utc, "UTC"),
            "timestamp_market": _dt(row.timestamp_utc, "America/New_York"),
            "timestamp_beijing": _dt(row.timestamp_utc, "Asia/Shanghai"),
            "timestamp": _dt(row.timestamp_utc, timezone_name),
            "open": str(row.open),
            "high": str(row.high),
            "low": str(row.low),
            "close": str(row.close),
            "volume": row.volume,
            "market_session": row.market_session,
            "adjustment_type": row.adjustment_type,
            "data_source": row.data_source,
        }
        for row in rows
    ]


@router.get("/history/summary")
def history_summary(db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            MarketBar.symbol,
            MarketBar.interval,
            func.count(MarketBar.id),
            func.min(MarketBar.timestamp_utc),
            func.max(MarketBar.timestamp_utc),
        ).group_by(MarketBar.symbol, MarketBar.interval)
    )
    return [
        {
            "symbol": symbol,
            "interval": interval,
            "count": count,
            "earliest": earliest,
            "latest": latest,
        }
        for symbol, interval, count, earliest, latest in rows
    ]


@router.get("/history/jobs")
def history_jobs(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(select(HistorySyncJob).order_by(desc(HistorySyncJob.id)).limit(limit))
    return [
        {
            "job_id": row.job_id,
            "symbol": row.symbol,
            "interval": row.interval,
            "status": row.status,
            "status_text": STATUS_TEXT.get(row.status, "未知状态"),
            "rows_inserted": row.rows_inserted,
            "rows_updated": row.rows_updated,
            "rows_skipped": row.rows_skipped,
            "error_code": row.error_code,
            "error_message": row.error_message,
        }
        for row in rows
    ]


@router.get("/history/issues")
def history_issues(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(select(HistoryDataIssue).order_by(desc(HistoryDataIssue.id)).limit(limit))
    return [
        {
            "symbol": row.symbol,
            "interval": row.interval,
            "issue_type": row.issue_type,
            "severity": row.severity,
            "message": row.message,
            "detected_at": row.detected_at,
        }
        for row in rows
    ]


@router.post("/history/sync")
def sync_history(
    request: HistorySyncRequest,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    if request.start.tzinfo is None or request.end.tzinfo is None:
        raise HTTPException(422, "开始和结束时间必须包含明确时区。")
    if request.start >= request.end:
        raise HTTPException(422, "开始时间必须早于结束时间。")
    service = HistoricalDataSyncService(db, build_history_provider(settings))
    jobs = []
    for symbol in request.symbols:
        for interval in request.intervals:
            jobs.append(
                service.sync_symbol(
                    symbol.upper(), interval, request.start, request.end,
                    request.adjustment_type, request.incremental, request.repair
                )
            )
    return [
        {
            "job_id": job.job_id,
            "symbol": job.symbol,
            "interval": job.interval,
            "status": job.status,
            "status_text": STATUS_TEXT.get(job.status, "未知状态"),
            "rows_inserted": job.rows_inserted,
            "rows_updated": job.rows_updated,
            "rows_skipped": job.rows_skipped,
        }
        for job in jobs
    ]
