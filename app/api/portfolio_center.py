from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.portfolio_center.errors import (
    DuplicatePortfolioName,
    DuplicateDefaultPortfolio,
    DuplicateSymbol,
    HoldingNotFound,
    PermissionDenied,
    PortfolioNotFound,
    ValidationError,
    WatchlistNotFound,
)
from app.portfolio_center.service import HoldingService, PortfolioService, PortfolioStatisticsService, WatchlistService


router = APIRouter(prefix="/api", tags=["Portfolio Center"], dependencies=[Depends(require_read)])
internal_router = APIRouter(
    prefix="/internal", tags=["Internal Portfolio Center"], dependencies=[Depends(require_admin)],
)


class CreatePortfolioRequest(BaseModel):
    user_id: str
    name: str
    description: Optional[str] = None
    currency: str = "USD"
    is_default: bool = False


class UpdatePortfolioRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[str] = None


class OpenHoldingRequest(BaseModel):
    symbol: str
    market: str = "US"
    direction: str = "LONG"
    quantity: Decimal
    average_cost: Decimal
    opened_at: Optional[datetime] = None
    trade_plan_id: Optional[int] = None
    user_position_id: Optional[int] = None
    notes: Optional[str] = None


class CloseHoldingRequest(BaseModel):
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None


class NotesRequest(BaseModel):
    notes: Optional[str] = None


class AddWatchlistRequest(BaseModel):
    symbol: str
    market: str = "US"
    notes: Optional[str] = None
    display_order: Optional[int] = None


class OrderRequest(BaseModel):
    display_order: int


@router.get("/portfolios")
def list_portfolios(
    user_id: Optional[str] = None, status: Optional[str] = None,
    default: Optional[bool] = None, page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200), db: Session = Depends(get_db),
):
    service = PortfolioService(db)
    try:
        rows = service.list_portfolios(user_id, status, default, page, page_size)
        total = service.count(user_id, status, default)
    except Exception as exc: _raise(exc)
    return {"items": [_portfolio(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    try: return _portfolio(PortfolioService(db).get(portfolio_id))
    except Exception as exc: _raise(exc)


@router.get("/portfolios/{portfolio_id}/holdings")
def list_holdings(
    portfolio_id: int, symbol: Optional[str] = None, market: Optional[str] = None,
    status: Optional[str] = None, direction: Optional[str] = None,
    opened_from: Optional[datetime] = None, opened_to: Optional[datetime] = None,
    closed_from: Optional[datetime] = None, closed_to: Optional[datetime] = None,
    page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = HoldingService(db)
    try:
        service.portfolios.get(portfolio_id)
        filters = dict(portfolio_id=portfolio_id, symbol=symbol.upper() if symbol else None,
                       market=market.upper() if market else None, status=status, direction=direction,
                       opened_from=opened_from, opened_to=opened_to,
                       closed_from=closed_from, closed_to=closed_to)
        rows = service.list_all(page=page, page_size=page_size, **filters)
        total = service.count(**filters)
    except Exception as exc: _raise(exc)
    return {"items": [_holding(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/holdings/{holding_id}")
def get_holding(holding_id: int, db: Session = Depends(get_db)):
    try: return _holding(HoldingService(db).get_holding(holding_id))
    except Exception as exc: _raise(exc)


@router.get("/portfolios/{portfolio_id}/watchlist")
def list_watchlist(
    portfolio_id: int, symbol: Optional[str] = None, market: Optional[str] = None,
    page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = WatchlistService(db)
    try:
        rows = service.list_symbols(portfolio_id, symbol, market, page, page_size)
        total = service.count(portfolio_id, symbol.upper() if symbol else None, market.upper() if market else None)
    except Exception as exc: _raise(exc)
    return {"items": [_watchlist(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/portfolios/{portfolio_id}/statistics")
def statistics(portfolio_id: int, db: Session = Depends(get_db)):
    try: return PortfolioStatisticsService(db).calculate(portfolio_id)
    except Exception as exc: _raise(exc)


@internal_router.post("/portfolios", include_in_schema=False)
def create_portfolio(request: CreatePortfolioRequest, db: Session = Depends(get_db)):
    try: return _portfolio(PortfolioService(db).create_portfolio(**request.model_dump()))
    except Exception as exc: _raise(exc)


@internal_router.patch("/portfolios/{portfolio_id}", include_in_schema=False)
def update_portfolio(portfolio_id: int, request: UpdatePortfolioRequest, db: Session = Depends(get_db)):
    try: return _portfolio(PortfolioService(db).update(portfolio_id, **request.model_dump(exclude_unset=True)))
    except Exception as exc: _raise(exc)


@internal_router.post("/portfolios/{portfolio_id}/set-default", include_in_schema=False)
def set_default(portfolio_id: int, db: Session = Depends(get_db)):
    try: return _portfolio(PortfolioService(db).set_default(portfolio_id))
    except Exception as exc: _raise(exc)


@internal_router.post("/portfolios/{portfolio_id}/holdings", include_in_schema=False)
def open_holding(portfolio_id: int, request: OpenHoldingRequest, db: Session = Depends(get_db)):
    try: return _holding(HoldingService(db).open_holding(portfolio_id, **request.model_dump()))
    except Exception as exc: _raise(exc)


@internal_router.post("/holdings/{holding_id}/close", include_in_schema=False)
def close_holding(holding_id: int, request: CloseHoldingRequest, db: Session = Depends(get_db)):
    try: return _holding(HoldingService(db).close_holding(holding_id, **request.model_dump()))
    except Exception as exc: _raise(exc)


@internal_router.patch("/holdings/{holding_id}/notes", include_in_schema=False)
def update_holding_notes(holding_id: int, request: NotesRequest, db: Session = Depends(get_db)):
    try: return _holding(HoldingService(db).update_notes(holding_id, request.notes))
    except Exception as exc: _raise(exc)


@internal_router.post("/portfolios/{portfolio_id}/watchlist", include_in_schema=False)
def add_watchlist(portfolio_id: int, request: AddWatchlistRequest, db: Session = Depends(get_db)):
    try: return _watchlist(WatchlistService(db).add_symbol(portfolio_id, **request.model_dump()))
    except Exception as exc: _raise(exc)


@internal_router.delete("/portfolios/{portfolio_id}/watchlist/{watchlist_id}", include_in_schema=False)
def remove_watchlist(portfolio_id: int, watchlist_id: int, db: Session = Depends(get_db)):
    try: return _watchlist(WatchlistService(db).remove_symbol(watchlist_id, portfolio_id))
    except Exception as exc: _raise(exc)


@internal_router.patch("/portfolios/{portfolio_id}/watchlist/{watchlist_id}/order", include_in_schema=False)
def reorder_watchlist(portfolio_id: int, watchlist_id: int, request: OrderRequest, db: Session = Depends(get_db)):
    try: return _watchlist(WatchlistService(db).move_order(watchlist_id, request.display_order, portfolio_id))
    except Exception as exc: _raise(exc)


def _portfolio(row):
    return {"id": row.id, "user_id": row.user_id, "name": row.name,
            "description": row.description, "currency": row.currency, "status": row.status,
            "is_default": row.is_default, "created_at": row.created_at, "updated_at": row.updated_at}


def _holding(row):
    return {"id": row.id, "portfolio_id": row.portfolio_id, "symbol": row.symbol,
            "market": row.market, "direction": row.direction, "quantity": str(row.quantity),
            "average_cost": str(row.average_cost), "status": row.status,
            "opened_at": row.opened_at, "closed_at": row.closed_at,
            "trade_plan_id": row.trade_plan_id, "user_position_id": row.user_position_id,
            "notes": row.notes, "created_at": row.created_at, "updated_at": row.updated_at}


def _watchlist(row):
    return {"id": row.id, "portfolio_id": row.portfolio_id, "symbol": row.symbol,
            "market": row.market, "display_order": row.display_order, "notes": row.notes,
            "created_at": row.created_at, "updated_at": row.updated_at}


def _raise(exc):
    if isinstance(exc, (PortfolioNotFound, HoldingNotFound, WatchlistNotFound)):
        raise HTTPException(404, str(exc))
    if isinstance(exc, PermissionDenied): raise HTTPException(403, str(exc))
    if isinstance(exc, (DuplicatePortfolioName, DuplicateSymbol)): raise HTTPException(409, str(exc))
    if isinstance(exc, (ValidationError, DuplicateDefaultPortfolio)): raise HTTPException(422, str(exc))
    raise exc
