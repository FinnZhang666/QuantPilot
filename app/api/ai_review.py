from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from app.ai.service import AIReviewService
from app.dashboard.auth import require_admin, require_read
from app.database.models import AIReviewAnalysis, Opportunity, OpportunityReview
from app.database.session import get_db

router = APIRouter(
    prefix="/api/ai-review", tags=["AI复盘分析"],
)


class RunRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    review_id: Optional[int] = None
    symbol: Optional[str] = None


@router.post("/run", dependencies=[Depends(require_admin)])
def run_ai_review(payload: RunRequest, db=Depends(get_db)):
    return AIReviewService(db).run(
        limit=payload.limit, review_id=payload.review_id, symbol=payload.symbol,
    )


@router.get("/pending", dependencies=[Depends(require_read)])
def pending_ai_reviews(
    limit: int = Query(20, ge=1, le=200), symbol: Optional[str] = None,
    db=Depends(get_db),
):
    service = AIReviewService(db)
    rows = service.pending(limit=limit, symbol=symbol)
    return {
        "items": [{
            "review_id": review.id, "opportunity_id": opportunity.id,
            "symbol": opportunity.symbol, "direction": opportunity.direction,
            "strategy": opportunity.strategy_name, "timeframe": opportunity.timeframe,
            "review_time": review.review_time,
        } for review, opportunity in rows],
        "total": len(rows), "enabled": service.settings.ai_review_enabled,
    }


@router.get("/statistics", dependencies=[Depends(require_read)])
def ai_review_statistics(include_mock: bool = False, db=Depends(get_db)):
    return AIReviewService(db).statistics(include_mock=include_mock)


@router.get("", dependencies=[Depends(require_read)])
def list_ai_reviews(
    symbol: Optional[str] = None, strategy: Optional[str] = None,
    timeframe: Optional[str] = None, direction: Optional[str] = None,
    status: Optional[str] = None, provider: Optional[str] = None,
    model: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db=Depends(get_db),
):
    filters = []
    if symbol:
        filters.append(Opportunity.symbol == symbol.upper().replace("US.", ""))
    if strategy:
        filters.append(Opportunity.strategy_name == strategy)
    if timeframe:
        filters.append(Opportunity.timeframe == timeframe)
    if direction:
        filters.append(Opportunity.direction == direction.upper())
    if status:
        filters.append(AIReviewAnalysis.status == status.upper())
    if provider:
        filters.append(AIReviewAnalysis.provider == provider)
    if model:
        filters.append(AIReviewAnalysis.model == model)
    query = select(AIReviewAnalysis, OpportunityReview, Opportunity).join(
        OpportunityReview, OpportunityReview.id == AIReviewAnalysis.opportunity_review_id,
    ).join(Opportunity, Opportunity.id == AIReviewAnalysis.opportunity_id)
    total = db.scalar(select(func.count()).select_from(AIReviewAnalysis).join(
        Opportunity, Opportunity.id == AIReviewAnalysis.opportunity_id,
    ).where(*filters)) or 0
    rows = db.execute(query.where(*filters).order_by(
        desc(AIReviewAnalysis.created_at),
    ).offset(offset).limit(limit))
    return {
        "items": [_serialize(analysis, review, opportunity) for analysis, review, opportunity in rows],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/{analysis_id}", dependencies=[Depends(require_read)])
def get_ai_review(analysis_id: int, db=Depends(get_db)):
    row = db.execute(select(AIReviewAnalysis, OpportunityReview, Opportunity).join(
        OpportunityReview, OpportunityReview.id == AIReviewAnalysis.opportunity_review_id,
    ).join(
        Opportunity, Opportunity.id == AIReviewAnalysis.opportunity_id,
    ).where(AIReviewAnalysis.id == analysis_id)).first()
    if row is None:
        raise HTTPException(404, "AI Review Analysis不存在。")
    return _serialize(row[0], row[1], row[2], detail=True)


@router.post("/{analysis_id}/retry", dependencies=[Depends(require_admin)])
def retry_ai_review(analysis_id: int, db=Depends(get_db)):
    try:
        row = AIReviewService(db).retry(analysis_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"id": row.id, "status": row.status, "error_message": row.error_message}


def _serialize(row, review, opportunity, detail=False):
    historical = row.historical_comparison_json or {}
    result = {
        "id": row.id, "opportunity_id": row.opportunity_id,
        "opportunity_review_id": row.opportunity_review_id,
        "symbol": opportunity.symbol, "direction": opportunity.direction,
        "strategy": opportunity.strategy_name, "timeframe": opportunity.timeframe,
        "review_return": _value(review.return_percent),
        "review_mfe": _value(review.mfe_percent), "review_mae": _value(review.mae_percent),
        "outcome_classification": historical.get("outcome_classification"),
        "confidence_score": row.confidence_score, "provider": row.provider,
        "model": row.model, "status": row.status, "created_at": row.created_at,
        "is_mock": row.provider == "mock",
    }
    if detail:
        result.update({
            "summary": row.summary, "outcome_explanation": row.outcome_explanation,
            "facts": historical.get("facts", []),
            "positive_factors": row.positive_factors_json,
            "negative_factors": row.negative_factors_json,
            "risk_factors": row.risk_factors_json,
            "timing_analysis": row.timing_analysis_json,
            "market_regime_analysis": row.market_regime_analysis_json,
            "historical_comparison": historical,
            "investigation_items": row.investigation_items_json,
            "uncertainty_notes": row.uncertainty_notes,
            "input_snapshot": row.input_snapshot_json,
            "runtime": {
                "started_at": row.started_at, "completed_at": row.completed_at,
                "latency_ms": row.latency_ms, "token_input": row.token_input,
                "token_output": row.token_output, "estimated_cost": _value(row.estimated_cost),
                "retry_count": row.retry_count,
            },
            "error": {"code": row.error_code, "message": row.error_message},
        })
    return result


def _value(value):
    return str(value) if value is not None else None
