from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.buy_score.service import BuyScoreService
from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db

router = APIRouter(prefix="/qmr", tags=["综合买入评分"])
internal_router = APIRouter(prefix="/internal/buy-scores", include_in_schema=False)


@router.get("/buy-scores", dependencies=[Depends(require_read)])
def buy_scores(symbol: Optional[str] = None,
               status: Optional[str] = Query(None, pattern="^(REJECT|WAIT|WATCH|EARLY_ENTRY|CONFIRMED_ENTRY|STRONG_ENTRY)$"),
               grade: Optional[str] = Query(None, pattern="^[SABCD]$"),
               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    items, total = BuyScoreService(db, settings).list(
        symbol=symbol, status=status, grade=grade, limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/ranking", dependencies=[Depends(require_read)])
def ranking(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    service = BuyScoreService(db, settings)
    rows, total = service.repository.rankings(service.config["version"], limit, offset)
    items = [{"rank_current": row.rank_current, "rank_previous": row.rank_previous,
              "rank_change": row.rank_change, "symbol": row.symbol,
              "final_buy_score": row.final_buy_score, "recovery_score": row.recovery_score,
              "mispricing_score": row.mispricing_score, "quality_score": row.quality_score,
              "data_confidence": row.data_confidence, "timestamp": row.evaluation_time}
             for row in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{symbol}/buy-score", dependencies=[Depends(require_read)])
def buy_score_detail(symbol: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    service = BuyScoreService(db, settings)
    history = service.detail(symbol)
    if not history:
        raise HTTPException(404, "该股票暂无综合买入评分。")
    return {"symbol": symbol.upper(), "latest": history[0], "history": history,
            "instrument_mappings": service.mappings(symbol)}


@internal_router.post("/run", dependencies=[Depends(require_admin)])
def run_buy_scores(dry_run: bool = True, symbol: Optional[str] = None,
                   evaluation_time: Optional[datetime] = None,
                   limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    if not settings.buy_score_enabled:
        raise HTTPException(409, "Buy Score Engine当前未启用。")
    return BuyScoreService(db, settings).run(evaluation_time, [symbol] if symbol else None, dry_run, limit)
