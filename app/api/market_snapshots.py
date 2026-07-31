from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dashboard.auth import require_admin
from app.database.session import get_db
from app.market_snapshot.service import MarketSnapshotService, SnapshotNotFound
from app.market_snapshot.models import snapshot_dict
from app.portfolio_center.errors import PortfolioNotFound, ValidationError


router = APIRouter(
    prefix="/api", tags=["Market Snapshot"], dependencies=[Depends(require_admin)],
)


@router.get("/market-snapshots")
def list_snapshots(
    symbol: Optional[str] = None, market: Optional[str] = None,
    holding: Optional[bool] = None, watching: Optional[bool] = None,
    candidate_signal: Optional[str] = None, trade_plan: Optional[str] = None,
    strategy_status: Optional[str] = None, page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200), db: Session = Depends(get_db),
):
    try:
        rows, total = MarketSnapshotService(db).list_snapshots(
            symbol, market, holding, watching, candidate_signal,
            trade_plan, strategy_status, page, page_size,
        )
    except (SnapshotNotFound, PortfolioNotFound, ValidationError) as exc:
        _raise(exc)
    return {"items": [snapshot_dict(row) for row in rows], "total": total,
            "page": page, "page_size": page_size}


@router.get("/market-snapshots/{symbol}")
def get_snapshot(symbol: str, market: str = "US", db: Session = Depends(get_db)):
    try:
        return snapshot_dict(MarketSnapshotService(db).get_snapshot(symbol, market))
    except (SnapshotNotFound, PortfolioNotFound, ValidationError) as exc:
        _raise(exc)


@router.get("/watchlists/{portfolio_id}/snapshots")
def watchlist_snapshots(
    portfolio_id: int, page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200), db: Session = Depends(get_db),
):
    try:
        rows, total = MarketSnapshotService(db).list_watchlist_snapshots(portfolio_id, page, page_size)
    except (SnapshotNotFound, PortfolioNotFound, ValidationError) as exc:
        _raise(exc)
    return {"items": [snapshot_dict(row) for row in rows], "total": total,
            "page": page, "page_size": page_size}


def _raise(exc):
    if isinstance(exc, (SnapshotNotFound, PortfolioNotFound)):
        raise HTTPException(404, str(exc))
    if isinstance(exc, ValidationError):
        raise HTTPException(422, str(exc))
    raise exc
