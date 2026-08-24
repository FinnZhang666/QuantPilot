from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.models import QmrBacktestCase, QmrBacktestResult
from app.database.session import get_db, get_session_factory
from app.qmr_backtest.service import QmrBacktestService

router = APIRouter(prefix="/qmr/backtest", tags=["QMR历史回测"])
internal_router = APIRouter(prefix="/internal/qmr/backtest", include_in_schema=False)


class QmrBacktestRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    parameter_set: str = "default"
    symbols: Optional[List[str]] = None
    dry_run: bool = False


def _execute_background(run_id):
    with get_session_factory()() as db:
        QmrBacktestService(db, get_settings()).execute(run_id)


@router.get("/runs", dependencies=[Depends(require_read)])
def list_runs(status: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
              offset: int = Query(0, ge=0), db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings)):
    items, total = QmrBacktestService(db, settings).list(status=status, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/compare", dependencies=[Depends(require_read)])
def compare_runs(run_ids: str = Query(..., pattern=r"^\d+(,\d+){1,4}$"),
                 db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    service = QmrBacktestService(db, settings)
    items = []
    for run_id in [int(value) for value in run_ids.split(",")]:
        try: items.append(service.get(run_id))
        except ValueError as exc: raise HTTPException(404, str(exc))
    return {"items": items, "comparison_fields": ["sample_count", "positive_rate",
        "average_return", "profit_factor", "max_drawdown", "strategy_status"]}


@router.get("/runs/{run_id}", dependencies=[Depends(require_read)])
def get_run(run_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    try: return QmrBacktestService(db, settings).get(run_id)
    except ValueError as exc: raise HTTPException(404, str(exc))


@router.get("/runs/{run_id}/cases", dependencies=[Depends(require_read)])
def get_cases(run_id: int, result: Optional[str] = None, entry_level: Optional[str] = None,
              limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db)):
    query = select(QmrBacktestCase).where(QmrBacktestCase.run_id == run_id)
    if result: query = query.where(QmrBacktestCase.result == result.upper())
    if entry_level: query = query.where(QmrBacktestCase.entry_level == entry_level.upper())
    rows = db.scalars(query.order_by(QmrBacktestCase.signal_time).offset(offset).limit(limit))
    return {"items": [_serialize(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/runs/{run_id}/results", dependencies=[Depends(require_read)])
def get_results(run_id: int, dimension: Optional[str] = None, db: Session = Depends(get_db)):
    query = select(QmrBacktestResult).where(QmrBacktestResult.run_id == run_id)
    if dimension: query = query.where(QmrBacktestResult.dimension == dimension.upper())
    rows = db.scalars(query.order_by(QmrBacktestResult.dimension, QmrBacktestResult.dimension_value,
                                      QmrBacktestResult.holding_period))
    return {"items": [_serialize(row) for row in rows]}


@internal_router.post("/runs", dependencies=[Depends(require_admin)])
def start_run(request: QmrBacktestRequest, tasks: BackgroundTasks,
              db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not settings.qmr_backtest_enabled: raise HTTPException(409, "QMR回测当前未启用。")
    try:
        result = QmrBacktestService(db, settings).prepare(request.start_time, request.end_time,
            request.parameter_set, request.symbols, request.dry_run)
    except ValueError as exc: raise HTTPException(400, str(exc))
    if result["run_id"] is not None: tasks.add_task(_execute_background, result["run_id"])
    return result


@internal_router.post("/runs/{run_id}/cancel", dependencies=[Depends(require_admin)])
def cancel_run(run_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    try: return QmrBacktestService(db, settings).cancel(run_id)
    except ValueError as exc: raise HTTPException(404, str(exc))


def _serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
