from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import BarInterval, FeatureJobType
from app.database.models import (
    FeatureCalculationJob, FeatureDefinitionRecord, FeatureQualityIssue,
    FeatureValueRecord,
)
from app.database.session import get_db
from app.features.pipeline import FeatureCalculationService
from app.features.registry import FeatureRegistry
from app.features.repository import FeatureRepository

router = APIRouter(prefix="/features", tags=["特征计算"])
ABSOLUTE_LIMIT = 5000
STATUS_TEXT = {"SUCCESS": "计算成功", "PARTIAL": "部分成功", "FAILED": "计算失败", "SKIPPED": "已跳过", "RUNNING": "计算中"}


class FeatureCalculateRequest(BaseModel):
    symbols: List[str] = Field(min_length=1, max_length=20)
    intervals: List[BarInterval] = Field(min_length=1, max_length=6)
    feature_names: List[str] = Field(min_length=1, max_length=100)
    start: datetime
    end: datetime
    repair: bool = False


def _value(row):
    for name in ("value_decimal", "value_integer", "value_boolean", "value_text"):
        value = getattr(row, name)
        if value is not None:
            return str(value) if name == "value_decimal" else value
    return None


@router.get("/definitions")
def definitions(db: Session = Depends(get_db)):
    rows = db.scalars(select(FeatureDefinitionRecord).where(FeatureDefinitionRecord.is_active.is_(True)).order_by(FeatureDefinitionRecord.feature_name))
    return [{"feature_name": row.feature_name, "display_name_zh": row.display_name_zh, "category": row.category, "required_bars": row.required_bars, "version": row.version, "value_type": row.value_type, "reference_symbol": row.reference_symbol} for row in rows]


@router.get("/latest")
def latest(symbol: str, interval: BarInterval, feature_names: Optional[str] = None, db: Session = Depends(get_db)):
    names = [item.strip() for item in feature_names.split(",")] if feature_names else None
    latest_times = select(
        FeatureValueRecord.feature_name,
        func.max(FeatureValueRecord.timestamp_utc).label("latest_time"),
    ).where(
        FeatureValueRecord.symbol == symbol.upper(),
        FeatureValueRecord.interval == interval.value,
    )
    if names:
        latest_times = latest_times.where(FeatureValueRecord.feature_name.in_(names))
    latest_times = latest_times.group_by(FeatureValueRecord.feature_name).subquery()
    query = select(FeatureValueRecord).join(
        latest_times,
        (FeatureValueRecord.feature_name == latest_times.c.feature_name) &
        (FeatureValueRecord.timestamp_utc == latest_times.c.latest_time),
    ).where(
        FeatureValueRecord.symbol == symbol.upper(),
        FeatureValueRecord.interval == interval.value,
    )
    rows = db.scalars(query.order_by(FeatureValueRecord.feature_name)).all()
    return [{"symbol": row.symbol, "interval": row.interval, "timestamp_utc": row.timestamp_utc, "feature_name": row.feature_name, "value": _value(row), "quality_status": row.quality_status, "quality_text": {"VALID": "有效", "WARMUP": "预热期", "MISSING": "缺失", "INVALID": "无效", "DEGRADED": "降级"}.get(row.quality_status, "未知"), "version": row.feature_version} for row in rows]


@router.get("/values")
def values(symbol: str, interval: BarInterval, feature_name: Optional[str] = None, start: Optional[datetime] = None, end: Optional[datetime] = None, limit: int = Query(1000, ge=1, le=ABSOLUTE_LIMIT), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = select(FeatureValueRecord).where(FeatureValueRecord.symbol == symbol.upper(), FeatureValueRecord.interval == interval.value)
    if feature_name:
        query = query.where(FeatureValueRecord.feature_name == feature_name)
    if start:
        query = query.where(FeatureValueRecord.timestamp_utc >= start)
    if end:
        query = query.where(FeatureValueRecord.timestamp_utc <= end)
    rows = db.scalars(query.order_by(FeatureValueRecord.timestamp_utc).offset(offset).limit(limit))
    return [{"timestamp_utc": row.timestamp_utc, "feature_name": row.feature_name, "value": _value(row), "quality_status": row.quality_status, "quality_message": row.quality_message, "version": row.feature_version, "parameters_hash": row.parameters_hash, "data_source": row.data_source} for row in rows]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    rows = db.execute(select(FeatureValueRecord.symbol, FeatureValueRecord.interval, func.count(), func.min(FeatureValueRecord.timestamp_utc), func.max(FeatureValueRecord.timestamp_utc)).group_by(FeatureValueRecord.symbol, FeatureValueRecord.interval))
    return [{"symbol": symbol, "interval": interval, "count": count, "earliest": earliest, "latest": latest} for symbol, interval, count, earliest, latest in rows]


@router.get("/jobs")
def jobs(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(select(FeatureCalculationJob).order_by(desc(FeatureCalculationJob.id)).limit(limit))
    return [{"job_id": row.job_id, "job_type": row.job_type, "status": row.status, "status_text": STATUS_TEXT.get(row.status, "未知状态"), "symbols": row.symbols_json, "intervals": row.intervals_json, "input_rows": row.input_rows, "output_rows": row.output_rows, "failed_features": row.failed_features, "metadata": row.metadata_json} for row in rows]


@router.get("/issues")
def issues(unresolved_only: bool = True, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    query = select(FeatureQualityIssue)
    if unresolved_only:
        query = query.where(FeatureQualityIssue.resolved_at.is_(None))
    rows = db.scalars(query.order_by(desc(FeatureQualityIssue.id)).limit(limit))
    return [{"symbol": row.symbol, "interval": row.interval, "feature_name": row.feature_name, "issue_type": row.issue_type, "severity": row.severity, "message": row.message, "detected_at": row.detected_at} for row in rows]


@router.post("/calculate")
def calculate(request: FeatureCalculateRequest, settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    if request.start.tzinfo is None or request.end.tzinfo is None:
        raise HTTPException(422, "开始和结束时间必须包含明确时区。")
    if request.start >= request.end:
        raise HTTPException(422, "开始时间必须早于结束时间。")
    maximum_days = {"1m": 60, "5m": 180, "15m": 365, "30m": 365, "60m": 730, "1d": 1825}
    span_days = (request.end - request.start).total_seconds() / 86400
    too_wide = [item.value for item in request.intervals if span_days > maximum_days[item.value]]
    if too_wide:
        raise HTTPException(422, "计算范围超过周期保护上限：" + "、".join(too_wide))
    registry = FeatureRegistry.defaults()
    unknown = [name for name in request.feature_names if name not in {item.feature_name for item in registry.list()}]
    if unknown:
        raise HTTPException(422, "未知特征：" + "、".join(unknown))
    unsupported = [
        "%s/%s" % (name, interval.value)
        for name in request.feature_names for interval in request.intervals
        if interval.value not in registry.get(name).supported_intervals
    ]
    if unsupported:
        raise HTTPException(422, "特征不支持所选周期：" + "、".join(unsupported))
    service = FeatureCalculationService(FeatureRepository(
        db, settings.feature_write_batch_size, settings.feature_read_chunk_size
    ), registry)
    result = []
    for symbol in request.symbols:
        for interval in request.intervals:
            job = service.calculate_symbol(symbol.upper(), interval, request.feature_names, request.start, request.end, FeatureJobType.REPAIR if request.repair else FeatureJobType.FULL)
            result.append({"job_id": job.job_id, "symbol": symbol.upper(), "interval": interval.value, "status": job.status, "status_text": STATUS_TEXT.get(job.status, "未知状态"), "input_rows": job.input_rows, "output_rows": job.output_rows})
    return result
