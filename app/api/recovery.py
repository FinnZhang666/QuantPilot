from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.qmr.service import QmrService
from app.recovery.service import RecoveryService

router = APIRouter(prefix="/qmr", tags=["止跌与资金回流"])
internal_router = APIRouter(prefix="/internal/recovery", include_in_schema=False)


@router.get("/recovery", dependencies=[Depends(require_read)])
def recovery_list(symbol: Optional[str] = None,
                  entry_status: Optional[str] = Query(None, pattern="^(WAIT|OBSERVE|EARLY_ENTRY|CONFIRMED_ENTRY|STRONG_ENTRY|FAILED)$"),
                  stage: Optional[str] = Query(None, pattern="^(PANIC|STABILIZING|EARLY_RECOVERY|RECOVERY_CONFIRMED|TREND_RECOVERY|FAILED_RECOVERY)$"),
                  limit: int = Query(100, ge=1, le=1000),
                  offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)):
    items, total = RecoveryService(db, settings).list(
        symbol=symbol, entry_status=entry_status, stage=stage, limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/recovery/{symbol}", dependencies=[Depends(require_read)])
def recovery_detail(symbol: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    service = RecoveryService(db, settings)
    history = service.detail(symbol)
    if not history:
        raise HTTPException(404, "该股票暂无Recovery评分。")
    qmr = QmrService(db, settings).detail(symbol)
    return {"symbol": symbol.upper(), "quality": None if not qmr else qmr[0]["quality_score"],
            "mispricing": None if not qmr else qmr[0]["mispricing_score"],
            "latest": history[0], "history": history, "events": service.event_history(symbol)}


@internal_router.post("/run", dependencies=[Depends(require_admin)])
def run_recovery(dry_run: bool = True, symbol: Optional[str] = None,
                 evaluation_time: Optional[datetime] = None,
                 limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    if not settings.recovery_enabled:
        raise HTTPException(409, "Recovery Engine当前未启用。")
    return RecoveryService(db, settings).run(
        evaluation_time=evaluation_time, symbols=[symbol] if symbol else None,
        dry_run=dry_run, limit=limit,
    )
