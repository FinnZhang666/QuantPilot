from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.universe.service import UniverseService

router = APIRouter(prefix="/universe", tags=["Universe"])
internal_router = APIRouter(prefix="/internal/universe", include_in_schema=False)


def _list(active_only, search, fund, sector, industry, status, sort, direction, limit, offset, db, settings):
    if active_only:
        status = "ACTIVE"
    items, total = UniverseService(db, settings).list(
        search=search, fund=fund, sector=sector, industry=industry, status=status,
        sort=sort, direction=direction, limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("", dependencies=[Depends(require_read)])
def list_universe(
    search: Optional[str] = None, fund: Optional[str] = None,
    sector: Optional[str] = None, industry: Optional[str] = None,
    status: Optional[str] = None, sort: str = "symbol", direction: str = "asc",
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    return _list(False, search, fund, sector, industry, status, sort, direction, limit, offset, db, settings)


@router.get("/active", dependencies=[Depends(require_read)])
def active_universe(
    search: Optional[str] = None, fund: Optional[str] = None,
    sector: Optional[str] = None, industry: Optional[str] = None,
    sort: str = "symbol", direction: str = "asc",
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    return _list(True, search, fund, sector, industry, None, sort, direction, limit, offset, db, settings)


@router.get("/{symbol}", dependencies=[Depends(require_read)])
def universe_detail(symbol: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    item = UniverseService(db, settings).get(symbol)
    if item is None:
        raise HTTPException(404, "该股票不在Universe历史记录中。")
    return item


@internal_router.post("/update", dependencies=[Depends(require_admin)])
def update_universe(force: bool = False, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not settings.universe_enabled:
        raise HTTPException(409, "Universe Engine当前未启用。")
    run = UniverseService(db, settings).update(force=force)
    return {"id": run.id, "status": run.status, "active_count": run.active_count,
            "added_count": run.added_count, "inactivated_count": run.inactivated_count,
            "error_count": run.error_count, "summary": run.summary_json}
