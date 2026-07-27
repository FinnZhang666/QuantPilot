from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.models import CandidateSignal, StrategyRun, WatchlistItem
from app.database.session import get_db
from app.strategy.service import StrategyRunner

router = APIRouter(prefix="/strategy", tags=["候选信号"])


class StrategyCalculateRequest(BaseModel):
    symbols: List[str] = Field(min_length=1, max_length=20)
    timeframes: List[str] = Field(min_length=1, max_length=6)
    mode: str = "incremental"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    auto_calculate_features: bool = True
    dry_run: bool = False
    confirm_large_run: bool = False


def _signal(row):
    return {
        "symbol": row.symbol, "market": row.market, "timeframe": row.timeframe,
        "bar_timestamp": row.bar_timestamp, "signal_type": row.signal_type,
        "score": row.score, "confidence": row.confidence, "status": row.status,
        "summary_zh": row.summary_zh, "reasons": row.reasons_json,
        "risks": row.risks_json, "feature_refs": row.feature_refs_json,
        "components": row.components_json, "parameters_hash": row.parameters_hash,
        "strategy_version": row.strategy_version,
    }


@router.get("/signals/latest")
def latest_signals(
    symbol: Optional[str] = None, role: Optional[str] = None,
    signal_type: Optional[str] = None, min_score: int = Query(0, ge=0, le=100),
    min_confidence: int = Query(0, ge=0, le=100), timeframe: Optional[str] = None,
    enabled_only: bool = True, db: Session = Depends(get_db),
):
    query = select(CandidateSignal).join(
        WatchlistItem, WatchlistItem.symbol == CandidateSignal.symbol,
    )
    if enabled_only:
        query = query.where(WatchlistItem.enabled.is_(True))
    if role:
        query = query.where(WatchlistItem.role == role)
    if symbol:
        query = query.where(CandidateSignal.symbol == symbol.upper().replace("US.", ""))
    if timeframe:
        query = query.where(CandidateSignal.timeframe == timeframe)
    if signal_type:
        query = query.where(CandidateSignal.signal_type == signal_type)
    query = query.where(
        CandidateSignal.score >= min_score,
        CandidateSignal.confidence >= min_confidence,
    ).order_by(desc(CandidateSignal.bar_timestamp))
    rows = db.scalars(query).all()
    found = {}
    for row in rows:
        found.setdefault((row.symbol, row.timeframe), row)
    return {"items": [_signal(row) for row in found.values()], "total": len(found)}


@router.get("/signals")
def signals(
    symbol: Optional[str] = None, timeframe: Optional[str] = None,
    signal_type: Optional[str] = None, status: Optional[str] = None,
    min_score: int = Query(0, ge=0, le=100), max_score: int = Query(100, ge=0, le=100),
    min_confidence: int = Query(0, ge=0, le=100),
    start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
    strategy_version: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = [CandidateSignal.score >= min_score, CandidateSignal.score <= max_score, CandidateSignal.confidence >= min_confidence]
    if symbol:
        filters.append(CandidateSignal.symbol == symbol.upper().replace("US.", ""))
    if timeframe:
        filters.append(CandidateSignal.timeframe == timeframe)
    if signal_type:
        filters.append(CandidateSignal.signal_type == signal_type)
    if status:
        filters.append(CandidateSignal.status == status)
    if start_time:
        filters.append(CandidateSignal.bar_timestamp >= start_time)
    if end_time:
        filters.append(CandidateSignal.bar_timestamp <= end_time)
    if strategy_version:
        filters.append(CandidateSignal.strategy_version == strategy_version)
    total = db.scalar(select(func.count()).select_from(CandidateSignal).where(*filters)) or 0
    rows = db.scalars(select(CandidateSignal).where(*filters).order_by(
        desc(CandidateSignal.bar_timestamp),
    ).offset(offset).limit(limit))
    return {"items": [_signal(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/signals/summary")
def signal_summary(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(
        CandidateSignal.signal_type, func.count(),
    ).group_by(CandidateSignal.signal_type)).all())
    return {
        "signal_type_counts": counts,
        "average_score": db.scalar(select(func.avg(CandidateSignal.score))),
        "average_confidence": db.scalar(select(func.avg(CandidateSignal.confidence))),
        "insufficient_data": counts.get("INSUFFICIENT_DATA", 0),
        "errors": db.scalar(select(func.count()).select_from(CandidateSignal).where(CandidateSignal.status == "ERROR")) or 0,
        "latest_calculated_at": db.scalar(select(func.max(CandidateSignal.updated_at))),
    }


@router.get("/runs")
def runs(
    status: Optional[str] = None, run_type: Optional[str] = None,
    start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(StrategyRun.status == status)
    if run_type:
        filters.append(StrategyRun.run_type == run_type.upper())
    if start_time:
        filters.append(StrategyRun.started_at >= start_time)
    if end_time:
        filters.append(StrategyRun.started_at <= end_time)
    total = db.scalar(select(func.count()).select_from(StrategyRun).where(*filters)) or 0
    rows = db.scalars(select(StrategyRun).where(*filters).order_by(desc(StrategyRun.id)).offset(offset).limit(limit))
    return {"items": [_run(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    row = db.scalar(select(StrategyRun).where(StrategyRun.run_id == run_id))
    if not row:
        raise HTTPException(404, "Strategy Run不存在。")
    return _run(row)


@router.post("/calculate")
def calculate_strategy(
    request: StrategyCalculateRequest, settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    try:
        return StrategyRunner(db, settings).run(
            request.symbols, request.timeframes, request.mode,
            request.start_time, request.end_time,
            request.auto_calculate_features, request.dry_run,
            request.confirm_large_run,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _run(row):
    return {
        "run_id": row.run_id, "run_type": row.run_type, "status": row.status,
        "symbols": row.symbols_json, "timeframes": row.timeframes_json,
        "started_at": row.started_at, "finished_at": row.finished_at,
        "bars_evaluated": row.bars_evaluated, "signals_written": row.signals_written,
        "signals_skipped": row.signals_skipped, "errors_count": row.errors_count,
        "elapsed_seconds": row.elapsed_seconds, "free_disk_gb": row.free_disk_gb,
        "error_summary": row.error_summary,
    }
