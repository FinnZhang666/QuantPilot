from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.market_context.service import MarketContextService


router = APIRouter(prefix="/api/market-context", tags=["QMR Market Context"],
                   include_in_schema=False)
internal_router = APIRouter(prefix="/internal/market-context", include_in_schema=False)


@router.get("/current", dependencies=[Depends(require_read)])
def current(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    service = MarketContextService(db, settings)
    global_row = service.repository.latest_global()
    return {"global": service.serialize_global(global_row),
            "sectors": [service.serialize_sector(service.repository.latest_sector(value))
                        for value in service.repository.sectors()]}


@router.get("/symbols/{symbol}", dependencies=[Depends(require_read)])
def symbol_context(symbol: str, db: Session = Depends(get_db),
                   settings: Settings = Depends(get_settings)):
    service = MarketContextService(db, settings)
    payload = service.current_for_symbol(symbol)
    if payload["global"] is None:
        raise HTTPException(404, "Market Context数据暂不可用。")
    return {"symbol": symbol.upper().removeprefix("US."), **payload}


@router.get("/history", dependencies=[Depends(require_read)])
def history(start: Optional[datetime] = None, end: Optional[datetime] = None,
            limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db),
            settings: Settings = Depends(get_settings)):
    service = MarketContextService(db, settings)
    rows = service.repository.historical_global(start, end)[-limit:]
    return {"items": [service.serialize_global(row) for row in rows], "total": len(rows)}


@internal_router.post("/evaluate", dependencies=[Depends(require_admin)])
def evaluate(dry_run: bool = True, session: str = "UNKNOWN",
             at: Optional[datetime] = None, db: Session = Depends(get_db),
             settings: Settings = Depends(get_settings)):
    if not settings.market_context_enabled:
        raise HTTPException(409, "Market Context Engine当前未启用。")
    return MarketContextService(db, settings).evaluate(at, session, persist=not dry_run)
