from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.backtest.service import BacktestService
from app.database.models import BacktestEquityPoint, BacktestRun, BacktestTrade
from app.database.session import get_db

router = APIRouter(prefix="/backtest", tags=["历史回测"])


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    run_mode: str = "SIGNAL_REPLAY"
    parameters_hash: Optional[str] = None
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    commission_per_trade: Decimal = Field(default=Decimal("0"), ge=0)
    commission_per_share: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_commission: Decimal = Field(default=Decimal("0"), ge=0)
    slippage_bps: Decimal = Field(default=Decimal("0"), ge=0, le=1000)
    force_close_at_end: bool = True


@router.post("/runs")
def run_backtest(request: BacktestRequest, db: Session = Depends(get_db)):
    try:
        return BacktestService(db).run(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/runs")
def list_runs(
    symbol: Optional[str] = None, status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    filters = []
    if symbol:
        filters.append(BacktestRun.symbol == symbol.upper().replace("US.", ""))
    if status:
        filters.append(BacktestRun.status == status.upper())
    total = db.scalar(select(func.count()).select_from(BacktestRun).where(*filters)) or 0
    rows = db.scalars(select(BacktestRun).where(*filters).order_by(
        desc(BacktestRun.id),
    ).offset(offset).limit(limit))
    return {"items": [_serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    row = db.get(BacktestRun, run_id)
    if not row:
        raise HTTPException(404, "回测任务不存在。")
    return _serialize(row)


@router.get("/runs/{run_id}/trades")
def get_trades(
    run_id: int, limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    rows = db.scalars(select(BacktestTrade).where(
        BacktestTrade.backtest_run_id == run_id,
    ).order_by(BacktestTrade.trade_number).offset(offset).limit(limit))
    return {"items": [_serialize(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/runs/{run_id}/equity")
def get_equity(
    run_id: int, limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    rows = db.scalars(select(BacktestEquityPoint).where(
        BacktestEquityPoint.backtest_run_id == run_id,
    ).order_by(BacktestEquityPoint.timestamp).offset(offset).limit(limit))
    return {"items": [_serialize(row) for row in rows], "limit": limit, "offset": offset}


def _serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
