from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.candidate_pool.service import CandidatePoolService
from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.models import CandidatePoolEntry, CandidatePoolRun, MarketRegime, Opportunity
from app.database.session import get_db

router = APIRouter(prefix="/api/candidate-pool", tags=["候选池"])


@router.get("", dependencies=[Depends(require_read)])
def list_entries(
    symbol: Optional[str] = None, direction: Optional[str] = None,
    source: Optional[str] = None, status: Optional[str] = None,
    min_score: int = Query(0, ge=0, le=100), pool_date: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = [CandidatePoolEntry.final_score >= min_score]
    if symbol:
        filters.append(CandidatePoolEntry.symbol == symbol.upper().replace("US.", ""))
    if direction:
        filters.append(CandidatePoolEntry.direction == direction.upper())
    if source:
        filters.append(CandidatePoolEntry.source_reference.contains(source.upper()))
    if status:
        filters.append(CandidatePoolEntry.status == status.upper())
    if pool_date:
        filters.append(CandidatePoolEntry.pool_date == pool_date)
    total = db.scalar(select(func.count()).select_from(CandidatePoolEntry).where(*filters)) or 0
    rows = db.scalars(select(CandidatePoolEntry).where(*filters).order_by(
        desc(CandidatePoolEntry.pool_date), CandidatePoolEntry.rank, CandidatePoolEntry.symbol,
    ).offset(offset).limit(limit))
    return {"items": [serialize_entry(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/runs", dependencies=[Depends(require_read)])
def runs(
    status: Optional[str] = None, run_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(CandidatePoolRun.status == status.upper())
    if run_type:
        filters.append(CandidatePoolRun.run_type == run_type.upper())
    total = db.scalar(select(func.count()).select_from(CandidatePoolRun).where(*filters)) or 0
    rows = db.scalars(select(CandidatePoolRun).where(*filters).order_by(
        desc(CandidatePoolRun.started_at),
    ).offset(offset).limit(limit))
    return {"items": [serialize_run(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}", dependencies=[Depends(require_read)])
def run_detail(run_id: int, db: Session = Depends(get_db)):
    row = db.get(CandidatePoolRun, run_id)
    if row is None:
        raise HTTPException(404, "Candidate Pool Run不存在。")
    return serialize_run(row)


@router.post("/build", dependencies=[Depends(require_admin)])
def build(
    pool_date: Optional[str] = None, db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.candidate_pool_enabled:
        raise HTTPException(409, "Candidate Pool当前未启用。")
    return serialize_run(CandidatePoolService(db, settings).build("MANUAL", pool_date))


@router.post("/refresh", dependencies=[Depends(require_admin)])
def refresh(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return serialize_run(CandidatePoolService(db, settings).refresh())


@router.post("/{entry_id}/expire", dependencies=[Depends(require_admin)])
def expire(entry_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    try:
        return serialize_entry(CandidatePoolService(db, settings).expire(entry_id))
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{entry_id}", dependencies=[Depends(require_read)])
def detail(entry_id: int, db: Session = Depends(get_db)):
    row = db.get(CandidatePoolEntry, entry_id)
    if row is None:
        raise HTTPException(404, "候选池条目不存在。")
    payload = serialize_entry(row)
    regime = db.get(MarketRegime, row.market_regime_id) if row.market_regime_id else None
    payload["market_regime"] = {
        "id": regime.id, "regime": regime.regime, "confidence": regime.confidence,
        "long_bias": regime.long_bias, "short_bias": regime.short_bias,
    } if regime else {"regime": "UNKNOWN"}
    opportunities = db.scalars(select(Opportunity).where(
        Opportunity.candidate_pool_entry_id == row.id,
    ).order_by(desc(Opportunity.detected_at)).limit(20)).all()
    payload["opportunities"] = [{
        "id": item.id, "direction": item.direction, "status": item.status,
        "score": item.score, "detected_at": item.detected_at,
    } for item in opportunities]
    return payload


def serialize_entry(row):
    return {
        "id": row.id, "symbol": row.symbol, "market": row.market,
        "asset_type": row.asset_type, "direction": row.direction,
        "source_type": row.source_type, "source_reference": row.source_reference,
        "pool_date": row.pool_date, "status": row.status,
        "long_score": row.long_score, "short_score": row.short_score,
        "final_score": row.final_score, "rank": row.rank,
        "market_regime_id": row.market_regime_id,
        "benchmark_symbol": row.benchmark_symbol,
        "sector_benchmark_symbol": row.sector_benchmark_symbol,
        "reason_snapshot": row.reason_snapshot_json,
        "filter_snapshot": row.filter_snapshot_json,
        "feature_snapshot": row.feature_snapshot_json,
        "first_seen_at": row.first_seen_at, "last_seen_at": row.last_seen_at,
        "expires_at": row.expires_at,
    }


def serialize_run(row):
    return {
        "id": row.id, "run_type": row.run_type, "market": row.market,
        "started_at": row.started_at, "completed_at": row.completed_at,
        "status": row.status, "universe_size": row.universe_size,
        "scanned_size": row.scanned_size, "candidate_count": row.candidate_count,
        "long_count": row.long_count, "short_count": row.short_count,
        "both_count": row.both_count, "regime_id": row.regime_id,
        "error_count": row.error_count, "summary": row.summary_json,
    }
