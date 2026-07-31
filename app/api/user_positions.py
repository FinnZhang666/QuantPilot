from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dashboard.auth import require_admin, require_read
from app.participation.service import UserParticipationService

router = APIRouter(
    prefix="/api/user-positions", tags=["User Participation"],
    dependencies=[Depends(require_read)],
)
internal_router = APIRouter(
    prefix="/internal/user-positions", tags=["Internal User Participation"],
    dependencies=[Depends(require_admin)],
)


class OpenPositionRequest(BaseModel):
    user_id: str
    trade_plan_id: str
    entry_price: str
    quantity: Optional[str] = None
    opened_at: Optional[datetime] = None
    source: str = "ADMIN_API"
    notes: Optional[str] = None


class ClosePositionRequest(BaseModel):
    position_id: int
    exit_price: str
    closed_at: Optional[datetime] = None
    notes: Optional[str] = None


@router.get("")
def list_positions(
    user_id: Optional[str] = None, symbol: Optional[str] = None,
    status: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    service = UserParticipationService(db)
    try:
        rows = service.list(user_id, symbol, status, limit, offset)
        total = service.count(user_id, symbol, status)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"items": [_serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/statistics")
def position_statistics(user_id: Optional[str] = None, db: Session = Depends(get_db)):
    return UserParticipationService(db).statistics(user_id)


@router.get("/{position_id}")
def get_position(position_id: int, db: Session = Depends(get_db)):
    service = UserParticipationService(db)
    row = service.get(position_id)
    if row is None:
        raise HTTPException(404, "User Position不存在。")
    plan = service.source_plan(row)
    result = _serialize(row)
    result["trade_plan"] = {
        "plan_id": plan.plan_id, "lifecycle_stage": plan.lifecycle_stage,
        "strategy_name": plan.strategy_name, "strategy_version": plan.strategy_version,
        "stop_loss_price": _decimal(plan.stop_loss_price),
        "target_prices": plan.target_prices_json or [],
    } if plan else None
    return result


@internal_router.post("/open", include_in_schema=False)
def open_position(request: OpenPositionRequest, db: Session = Depends(get_db)):
    try:
        row = UserParticipationService(db).open(**request.model_dump())
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return _serialize(row)


@internal_router.post("/close", include_in_schema=False)
def close_position(request: ClosePositionRequest, db: Session = Depends(get_db)):
    try:
        row = UserParticipationService(db).close(**request.model_dump())
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return _serialize(row)


def _decimal(value):
    return str(value) if value is not None else None


def _serialize(row):
    return {
        "id": row.id, "user_id": row.user_id, "trade_plan_id": row.trade_plan_id,
        "symbol": row.symbol, "direction": row.direction,
        "entry_price": _decimal(row.entry_price), "quantity": _decimal(row.quantity),
        "opened_at": row.opened_at, "closed_at": row.closed_at,
        "exit_price": _decimal(row.exit_price), "status": row.status,
        "source": row.source, "notes": row.notes,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }
