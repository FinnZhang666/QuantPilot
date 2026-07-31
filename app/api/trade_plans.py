from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import TradePlan
from app.database.session import get_db
from app.dashboard.auth import require_read
from app.trade_lifecycle.service import TradeLifecycleService

router = APIRouter(
    prefix="/api/trade-plans", tags=["Trade Lifecycle"],
    dependencies=[Depends(require_read)],
)


@router.get("")
def list_trade_plans(
    symbol: Optional[str] = None, lifecycle_stage: Optional[str] = None,
    status: Optional[str] = None, strategy: Optional[str] = None,
    market: Optional[str] = None, start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    service = TradeLifecycleService(db)
    try:
        rows = service.list(
            symbol, lifecycle_stage, status, strategy, market,
            start_time, end_time, limit, offset,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    filters = []
    if symbol:
        filters.append(TradePlan.symbol == symbol.upper().replace("US.", ""))
    if lifecycle_stage:
        filters.append(TradePlan.lifecycle_stage == lifecycle_stage.upper())
    if status:
        filters.append(TradePlan.plan_status == status.upper())
    if strategy:
        filters.append(TradePlan.strategy_name == strategy)
    if market:
        filters.append(TradePlan.market == market.upper())
    if start_time:
        filters.append(TradePlan.created_at >= start_time)
    if end_time:
        filters.append(TradePlan.created_at <= end_time)
    total = db.scalar(select(func.count()).select_from(TradePlan).where(*filters)) or 0
    return {
        "items": [_serialize(row) for row in rows],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/{plan_id}")
def get_trade_plan(plan_id: str, db: Session = Depends(get_db)):
    row = TradeLifecycleService(db).get(plan_id)
    if row is None:
        raise HTTPException(404, "Trade Plan不存在。")
    return _serialize(row)


@router.get("/{plan_id}/history")
def get_trade_plan_history(plan_id: str, db: Session = Depends(get_db)):
    try:
        rows = TradeLifecycleService(db).history(plan_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
    return {"items": [_serialize_transition(row) for row in rows]}


def _decimal(value):
    return str(value) if value is not None else None


def _serialize(row: TradePlan):
    return {
        "id": row.id, "plan_id": row.plan_id, "symbol": row.symbol,
        "market": row.market, "strategy_name": row.strategy_name,
        "strategy_version": row.strategy_version, "signal_id": row.signal_id,
        "lifecycle_stage": row.lifecycle_stage, "direction": row.direction,
        "timeframe": row.timeframe, "created_at": row.created_at,
        "updated_at": row.updated_at, "reference_price": _decimal(row.reference_price),
        "buy_zone": {
            "lower": _decimal(row.buy_zone_lower), "upper": _decimal(row.buy_zone_upper),
        },
        "trend_add_on_zone": {
            "lower": _decimal(row.trend_add_on_zone_lower),
            "upper": _decimal(row.trend_add_on_zone_upper),
        },
        "breakout_zone": {
            "lower": _decimal(row.breakout_zone_lower),
            "upper": _decimal(row.breakout_zone_upper),
        },
        "stop_loss_price": _decimal(row.stop_loss_price),
        "target_prices": row.target_prices_json or [],
        "invalidation_condition": row.invalidation_condition,
        "confidence": row.confidence, "score": row.score,
        "plan_status": row.plan_status,
        "source_metadata": row.source_metadata_json,
        "user_participation_status": row.user_participation_status,
        "review_status": row.review_status,
    }


def _serialize_transition(row):
    return {
        "id": row.id, "previous_stage": row.previous_stage,
        "new_stage": row.new_stage, "transitioned_at": row.transitioned_at,
        "reason": row.reason, "source": row.source, "metadata": row.metadata_json,
    }
