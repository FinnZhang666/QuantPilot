from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import StrategyParameterSet, WatchlistItem, WatchlistTimeframe
from app.database.session import get_db
from app.strategy.constants import STRATEGY_NAME, STRATEGY_VERSION
from app.strategy.watchlist import WatchlistService

router = APIRouter(prefix="/watchlist", tags=["观察池"])


class AddWatchlistRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=18)
    market: str = "US"
    notes: Optional[str] = None


class UpdateWatchlistRequest(BaseModel):
    role: Optional[str] = None
    benchmark_symbol: Optional[str] = None
    strategy_template: Optional[str] = None
    sector: Optional[str] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None


class ReclassifyRequest(BaseModel):
    confirm: bool = False


class ParameterUpdateRequest(BaseModel):
    parameters: Dict[str, object]


def _business_error(exc: Exception):
    if isinstance(exc, KeyError):
        raise HTTPException(404, str(exc).strip("'"))
    raise HTTPException(400, str(exc))


@router.get("")
def list_watchlist(
    enabled_only: bool = False, role: Optional[str] = None,
    validation_status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    service = WatchlistService(db)
    rows = service.list_symbols(enabled_only, role, validation_status)
    return {
        "items": [service.serialize(item) for item in rows[offset:offset + limit]],
        "total": len(rows), "limit": limit, "offset": offset,
    }


@router.get("/{symbol}")
def get_watchlist_symbol(symbol: str, db: Session = Depends(get_db)):
    service = WatchlistService(db)
    try:
        item = service.get_symbol(symbol)
    except ValueError as exc:
        _business_error(exc)
    if not item:
        raise HTTPException(404, "Ticker不存在于观察池中。")
    output = service.serialize(item)
    output["timeframes"] = list(db.scalars(select(WatchlistTimeframe.timeframe).where(
        WatchlistTimeframe.watchlist_item_id == item.id,
        WatchlistTimeframe.enabled.is_(True),
    )))
    return output


@router.post("")
def add_watchlist(request: AddWatchlistRequest, db: Session = Depends(get_db)):
    try:
        return WatchlistService(db).add_symbol(request.symbol, request.market, request.notes)
    except Exception as exc:
        _business_error(exc)


@router.patch("/{symbol}")
def update_watchlist(symbol: str, request: UpdateWatchlistRequest, db: Session = Depends(get_db)):
    changes = request.model_dump(exclude_unset=True)
    try:
        item = WatchlistService(db).update_symbol(symbol, **changes)
        return WatchlistService.serialize(item, "updated")
    except Exception as exc:
        _business_error(exc)


@router.delete("/{symbol}")
def remove_watchlist(symbol: str, db: Session = Depends(get_db)):
    try:
        return WatchlistService.serialize(WatchlistService(db).remove_symbol(symbol), "disabled")
    except Exception as exc:
        _business_error(exc)


@router.post("/{symbol}/enable")
def enable_watchlist(symbol: str, db: Session = Depends(get_db)):
    try:
        return WatchlistService.serialize(WatchlistService(db).enable_symbol(symbol), "enabled")
    except Exception as exc:
        _business_error(exc)


@router.post("/{symbol}/disable")
def disable_watchlist(symbol: str, db: Session = Depends(get_db)):
    try:
        return WatchlistService.serialize(WatchlistService(db).disable_symbol(symbol), "disabled")
    except Exception as exc:
        _business_error(exc)


@router.post("/{symbol}/reclassify")
def reclassify_watchlist(symbol: str, request: ReclassifyRequest, db: Session = Depends(get_db)):
    try:
        return WatchlistService(db).reclassify_symbol(symbol, request.confirm)
    except Exception as exc:
        _business_error(exc)


@router.get("/{symbol}/parameters")
def get_parameters(symbol: str, db: Session = Depends(get_db)):
    service = WatchlistService(db)
    item = service.get_symbol(symbol)
    if not item:
        raise HTTPException(404, "Ticker不存在于观察池中。")
    row = db.scalar(select(StrategyParameterSet).where(
        StrategyParameterSet.watchlist_item_id == item.id,
        StrategyParameterSet.strategy_name == STRATEGY_NAME,
        StrategyParameterSet.strategy_version == STRATEGY_VERSION,
        StrategyParameterSet.enabled.is_(True),
    ))
    return {
        "symbol": item.symbol, "strategy_name": row.strategy_name,
        "strategy_version": row.strategy_version, "parameters": row.parameters_json,
        "parameters_hash": row.parameters_hash,
        "parameter_status": row.parameters_json.get("parameter_status"),
    }


@router.patch("/{symbol}/parameters")
def update_parameters(symbol: str, request: ParameterUpdateRequest, db: Session = Depends(get_db)):
    try:
        return WatchlistService(db).update_parameters(symbol, request.parameters)
    except Exception as exc:
        _business_error(exc)
