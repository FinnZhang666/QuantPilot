from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dashboard.auth import require_admin, require_read
from app.trade_review.runtime import TradeReviewRuntime
from app.trade_review.service import TradeReviewService

router = APIRouter(
    prefix="/api/reviews", tags=["Trade Review"],
    dependencies=[Depends(require_read)],
)
internal_router = APIRouter(
    prefix="/internal/reviews", tags=["Internal Trade Review"],
    dependencies=[Depends(require_admin)],
)


class GenerateReviewsRequest(BaseModel):
    dry_run: bool = True
    limit: int = Field(100, ge=1, le=1000)
    symbol: Optional[str] = None
    strategy: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@router.get("")
def list_reviews(
    review_type: Optional[str] = None, result: Optional[str] = None,
    symbol: Optional[str] = None, strategy: Optional[str] = None,
    start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    service = TradeReviewService(db)
    try:
        rows = service.list(
            review_type, result, symbol, strategy, start_time, end_time, limit, offset,
        )
        total = service.count(review_type, result, symbol, strategy, start_time, end_time)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {
        "items": [_serialize(row, service.source_plan(row)) for row in rows],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/statistics")
def review_statistics(db: Session = Depends(get_db)):
    return TradeReviewService(db).statistics()


@router.get("/{review_id}")
def get_review(review_id: int, db: Session = Depends(get_db)):
    service = TradeReviewService(db)
    row = service.get(review_id)
    if row is None:
        raise HTTPException(404, "Trade Review不存在。")
    return _serialize(row, service.source_plan(row))


@internal_router.post("/generate", include_in_schema=False)
def generate_reviews(request: GenerateReviewsRequest, db: Session = Depends(get_db)):
    try:
        return TradeReviewRuntime(db).generate_reviews(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _value(value):
    return str(value) if value is not None else None


def _serialize(row, plan):
    return {
        "id": row.id, "review_key": row.review_key,
        "trade_plan_id": plan.plan_id if plan else row.trade_plan_id,
        "user_position_id": row.user_position_id,
        "system_paper_position_id": row.system_paper_position_id,
        "symbol": plan.symbol if plan else None,
        "strategy_name": plan.strategy_name if plan else None,
        "strategy_version": plan.strategy_version if plan else None,
        "timeframe": plan.timeframe if plan else None,
        "direction": plan.direction if plan else None,
        "review_type": row.review_type, "result": row.result,
        "entry_price": _value(row.entry_price), "exit_price": _value(row.exit_price),
        "mfe": _value(row.mfe), "mae": _value(row.mae),
        "holding_minutes": row.holding_minutes,
        "target_hit": row.target_hit, "stop_hit": row.stop_hit,
        "realized_return": _value(row.realized_return),
        "exit_reason": row.exit_reason,
        "fill_model_version": row.fill_model_version,
        "data_quality": row.data_quality,
        "review_time": row.review_time,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }
