from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.qmr.service import QmrService

router = APIRouter(prefix="/qmr", tags=["优质错杀"])
internal_router = APIRouter(prefix="/internal/qmr", include_in_schema=False)


@router.get("/candidates", dependencies=[Depends(require_read)])
def candidates(status: Optional[str] = "WATCH", symbol: Optional[str] = None,
               sort: str = Query("combined", pattern="^(quality|mispricing|combined)$"),
               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    items, total = QmrService(db, settings).list(status=status, symbol=symbol, sort=sort, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{symbol}", dependencies=[Depends(require_read)])
def detail(symbol: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    items = QmrService(db, settings).detail(symbol)
    if not items: raise HTTPException(404, "该股票暂无QMR评分。")
    return {"symbol": symbol.upper(), "latest": items[0], "history": items}


@internal_router.post("/run", dependencies=[Depends(require_admin)])
def run_qmr(dry_run: bool = True, symbol: Optional[str] = None,
            evaluation_time: Optional[datetime] = None, limit: int = Query(100, ge=1, le=1000),
            db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not settings.qmr_enabled: raise HTTPException(409, "QMR Engine当前未启用。")
    return QmrService(db, settings).run(evaluation_time, [symbol] if symbol else None, dry_run, limit)
