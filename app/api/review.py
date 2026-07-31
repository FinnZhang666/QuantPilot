from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.dashboard.auth import require_admin, require_read
from app.database.models import Opportunity, OpportunityReview, ReviewStatistic
from app.database.session import get_db
from app.review.service import OpportunityReviewService

router = APIRouter(
    prefix="/api/review", tags=["Opportunity复盘"],
)


@router.post("/run", dependencies=[Depends(require_admin)])
def run_reviews(
    limit: int = Query(100, ge=1, le=1000), symbol: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return OpportunityReviewService(db).run(limit=limit, symbol=symbol)


@router.get("/pending", dependencies=[Depends(require_read)])
def pending_reviews(
    limit: int = Query(100, ge=1, le=1000), symbol: Optional[str] = None,
    db: Session = Depends(get_db),
):
    rows = OpportunityReviewService(db).pending(limit=limit, symbol=symbol)
    return {
        "items": [_opportunity(row) for row in rows],
        "total": len(rows), "limit": limit,
    }


@router.get("/statistics", dependencies=[Depends(require_read)])
def review_statistics(db: Session = Depends(get_db)):
    rows = db.scalars(select(ReviewStatistic).order_by(
        ReviewStatistic.strategy_name, ReviewStatistic.timeframe, ReviewStatistic.symbol,
    ))
    return {"items": [_statistic(row) for row in rows]}


@router.get("", dependencies=[Depends(require_read)])
def list_reviews(
    status: Optional[str] = None, symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = []
    if status:
        filters.append(OpportunityReview.review_status == status.upper())
    if symbol:
        filters.append(Opportunity.symbol == symbol.upper().replace("US.", ""))
    base = select(OpportunityReview, Opportunity).join(Opportunity)
    total = db.scalar(select(func.count()).select_from(OpportunityReview).join(
        Opportunity,
    ).where(*filters)) or 0
    rows = db.execute(base.where(*filters).order_by(
        desc(OpportunityReview.review_time),
    ).offset(offset).limit(limit))
    return {
        "items": [_review(review, opportunity) for review, opportunity in rows],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/{review_id}", dependencies=[Depends(require_read)])
def get_review(review_id: int, db: Session = Depends(get_db)):
    row = db.execute(select(OpportunityReview, Opportunity).join(
        Opportunity,
    ).where(OpportunityReview.id == review_id)).first()
    if row is None:
        raise HTTPException(404, "Opportunity Review不存在。")
    return _review(row[0], row[1], detail=True)


def _review(row, opportunity, detail=False):
    result = {
        "id": row.id, "opportunity_id": row.opportunity_id,
        "symbol": opportunity.symbol, "timeframe": opportunity.timeframe,
        "direction": opportunity.direction, "strategy_name": opportunity.strategy_name,
        "status": row.review_status, "review_time": row.review_time,
        "review_window": row.review_window, "holding_bars": row.holding_bars,
        "holding_minutes": row.holding_minutes,
        "return_percent": _value(row.return_percent),
        "mfe_percent": _value(row.mfe_percent), "mae_percent": _value(row.mae_percent),
        "target_hit": row.target_hit, "stop_hit": row.stop_hit,
    }
    if detail:
        result.update({
            "entry_reference_price": _value(row.entry_reference_price),
            "exit_reference_price": _value(row.exit_reference_price),
            "last_price": _value(row.last_price),
            "max_close_return": _value(row.max_close_return),
            "min_close_return": _value(row.min_close_return),
            "holding_days": _value(row.holding_days),
            "price_path": row.price_path_json, "statistics": row.statistics_json,
            "reason": row.reason_json,
        })
    return result


def _opportunity(row):
    return {
        "id": row.id, "symbol": row.symbol, "timeframe": row.timeframe,
        "direction": row.direction, "status": row.status,
        "bar_time": row.bar_time, "expiry_at": row.expiry_at,
    }


def _statistic(row):
    return {
        "strategy_name": row.strategy_name, "strategy_version": row.strategy_version,
        "timeframe": row.timeframe, "symbol": row.symbol,
        "total_reviews": row.total_reviews, "long_count": row.long_count,
        "short_count": row.short_count, "success_rate": _value(row.success_rate),
        "average_return": _value(row.average_return),
        "average_mfe": _value(row.average_mfe), "average_mae": _value(row.average_mae),
        "maximum_return": _value(row.maximum_return),
        "maximum_drawdown": _value(row.maximum_drawdown),
        "review_coverage_rate": _value(row.review_coverage_rate),
        "data_insufficient_count": row.data_insufficient_count,
    }


def _value(value):
    return str(value) if value is not None else None
