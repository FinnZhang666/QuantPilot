from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database.models import Opportunity
from app.database.session import get_db
from app.dashboard.auth import require_read

router = APIRouter(
    prefix="/api/opportunities", tags=["实时机会"],
    dependencies=[Depends(require_read)],
)


@router.get("")
def list_opportunities(
    symbol: Optional[str] = None, timeframe: Optional[str] = None,
    direction: Optional[str] = None, status: Optional[str] = None,
    strategy_name: Optional[str] = None, min_score: int = Query(0, ge=0, le=100),
    start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = []
    if symbol:
        filters.append(Opportunity.symbol == symbol.upper().replace("US.", ""))
    if status:
        filters.append(Opportunity.status == status.upper())
    if timeframe:
        filters.append(Opportunity.timeframe == timeframe)
    if direction:
        filters.append(Opportunity.direction == direction.upper())
    if strategy_name:
        filters.append(Opportunity.strategy_name == strategy_name)
    filters.append(Opportunity.score >= min_score)
    if start_time:
        filters.append(Opportunity.detected_at >= start_time)
    if end_time:
        filters.append(Opportunity.detected_at <= end_time)
    total = db.scalar(select(func.count()).select_from(Opportunity).where(*filters)) or 0
    rows = db.scalars(select(Opportunity).where(*filters).order_by(
        desc(Opportunity.detected_at),
    ).offset(offset).limit(limit))
    return {"items": [_serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    row = db.get(Opportunity, opportunity_id)
    if row is None:
        raise HTTPException(404, "Opportunity不存在。")
    return _serialize(row)


@router.get("/symbol/{symbol}")
def symbol_opportunities(
    symbol: str, limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(Opportunity).where(
        Opportunity.symbol == symbol.upper().replace("US.", ""),
    ).order_by(desc(Opportunity.detected_at)).limit(limit))
    return {"items": [_serialize(row) for row in rows]}


def _serialize(row):
    return {
        "id": row.id, "symbol": row.symbol, "timeframe": row.timeframe,
        "direction": row.direction, "opportunity_type": row.opportunity_type,
        "strategy_name": row.strategy_name, "strategy_version": row.strategy_version,
        "signal_id": row.signal_id, "market_regime": row.market_regime,
        "status": row.status, "score": row.score, "confidence": row.confidence,
        "detected_at": row.detected_at, "bar_time": row.bar_time,
        "entry_reference_price": str(row.entry_reference_price),
        "stop_reference_price": str(row.stop_reference_price) if row.stop_reference_price is not None else None,
        "target_reference_price": str(row.target_reference_price) if row.target_reference_price is not None else None,
        "expiry_at": row.expiry_at, "feature_snapshot": row.feature_snapshot_json,
        "strategy_snapshot": row.strategy_snapshot_json,
        "decision_snapshot": row.decision_snapshot_json,
        "notification_status": row.notification_status,
        "notification_message_id": row.notification_message_id,
    }
