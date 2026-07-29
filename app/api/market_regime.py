from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.models import MarketRegime
from app.database.session import get_db
from app.market_regime.service import MarketRegimeService

router = APIRouter(prefix="/api/market-regime", tags=["市场状态"])


@router.get("/current", dependencies=[Depends(require_read)])
def current(db: Session = Depends(get_db)):
    row = db.scalar(select(MarketRegime).order_by(desc(MarketRegime.bar_time)).limit(1))
    return serialize(row) if row else {"regime": "UNKNOWN", "data_sufficient": False}


@router.get("/history", dependencies=[Depends(require_read)])
def history(
    regime: Optional[str] = None, start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    filters = []
    if regime:
        filters.append(MarketRegime.regime == regime.upper())
    if start_time:
        filters.append(MarketRegime.bar_time >= start_time)
    if end_time:
        filters.append(MarketRegime.bar_time <= end_time)
    total = db.scalar(select(func.count()).select_from(MarketRegime).where(*filters)) or 0
    rows = db.scalars(select(MarketRegime).where(*filters).order_by(
        desc(MarketRegime.bar_time),
    ).offset(offset).limit(limit))
    return {"items": [serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/evaluate", dependencies=[Depends(require_admin)])
def evaluate(
    force: bool = False, db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.market_regime_enabled:
        raise HTTPException(409, "Market Regime功能当前未启用。")
    return serialize(MarketRegimeService(db, settings).evaluate(force=force))


def serialize(row):
    reasons = row.reason_snapshot_json or {}
    return {
        "id": row.id, "market": row.market, "timeframe": row.timeframe,
        "regime": row.regime, "trend_score": row.trend_score,
        "breadth_score": row.breadth_score, "momentum_score": row.momentum_score,
        "volatility_score": row.volatility_score, "risk_score": row.risk_score,
        "long_bias": row.long_bias, "short_bias": row.short_bias,
        "confidence": row.confidence, "benchmark_symbol": row.benchmark_symbol,
        "sector_benchmark_symbol": row.sector_benchmark_symbol,
        "evaluated_at": row.evaluated_at, "bar_time": row.bar_time,
        "valid_until": row.valid_until, "feature_snapshot": row.feature_snapshot_json,
        "reason_snapshot": reasons, "data_sufficient": reasons.get("data_sufficient", False),
    }
