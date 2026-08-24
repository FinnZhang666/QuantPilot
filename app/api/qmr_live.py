from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.qmr_live.repository import QmrLiveRepository
from app.qmr_live.service import QmrLiveSignalService
from app.qmr_live.tracking import QmrPerformanceTracker


router = APIRouter(prefix="/qmr/live-signals", tags=["QMR实盘信号"])
internal_router = APIRouter(prefix="/internal/qmr/live", include_in_schema=False)


class QmrLiveRunRequest(BaseModel):
    evaluation_time: Optional[datetime] = None


def serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.get("", dependencies=[Depends(require_read)])
def list_signals(symbol: Optional[str] = None, level: Optional[str] = None,
                 status: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
                 offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    rows, total = QmrLiveRepository(db).list_signals(symbol, level, status, limit, offset)
    return {"items": [serialize(row) for row in rows], "total": total,
            "limit": limit, "offset": offset}


@router.get("/statistics", dependencies=[Depends(require_read)])
def statistics(window_days: int = Query(5, ge=1, le=20),
               db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    tracker = QmrPerformanceTracker(db, settings)
    return {"performance": tracker.statistics(window_days), "validation": tracker.validation()}


@router.get("/{signal_id}", dependencies=[Depends(require_read)])
def signal_detail(signal_id: str, db: Session = Depends(get_db)):
    repository = QmrLiveRepository(db)
    signal = repository.signal(signal_id)
    if signal is None:
        raise HTTPException(404, "QMR Signal不存在。")
    return {"signal": serialize(signal),
            "performance": [serialize(row) for row in repository.performances(signal.signal_id)],
            "feedback": repository.feedback_counts(signal.signal_id)}


@internal_router.post("/run", dependencies=[Depends(require_admin)])
def run_live(request: QmrLiveRunRequest, db: Session = Depends(get_db),
             settings: Settings = Depends(get_settings)):
    if not settings.qmr_live_enabled:
        raise HTTPException(409, "QMR实盘信号当前未启用。")
    return QmrLiveSignalService(db, settings).run(request.evaluation_time)


@internal_router.post("/track", dependencies=[Depends(require_admin)])
def track_live(request: QmrLiveRunRequest, db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings)):
    return QmrPerformanceTracker(db, settings).run(request.evaluation_time)
