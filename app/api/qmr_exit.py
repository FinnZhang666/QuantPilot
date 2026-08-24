from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.qmr_exit.service import QmrExitService


router = APIRouter(prefix="/api/qmr/exit", tags=["QMR Exit"])
internal_router = APIRouter(prefix="/internal/qmr/exit", include_in_schema=False)


@router.get("", dependencies=[Depends(require_read)])
def list_exit_evaluations(symbol: str = None, state: str = None,
                          limit: int = Query(100, ge=1, le=500),
                          db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    service = QmrExitService(db, settings)
    rows = service.repository.list(symbol=symbol, state=state, limit=limit)
    return {"items": [service.serialize(row) for row in rows], "total": len(rows)}


@router.get("/{evaluation_id}", dependencies=[Depends(require_read)])
def get_exit_evaluation(evaluation_id: int, db: Session = Depends(get_db),
                        settings: Settings = Depends(get_settings)):
    from app.database.models import QmrExitEvaluation
    row = db.get(QmrExitEvaluation, evaluation_id)
    if row is None:
        raise HTTPException(404, "QMR退出评估不存在。")
    return QmrExitService.serialize(row)


@internal_router.post("/run", dependencies=[Depends(require_admin)])
def run_exit_engine(symbol: str = None, evaluation_time: datetime = None,
                    dry_run: bool = True, limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not settings.qmr_exit_enabled:
        raise HTTPException(409, "QMR Exit Engine已停用。")
    return QmrExitService(db, settings).run(symbol=symbol, evaluation_time=evaluation_time,
                                             dry_run=dry_run, limit=limit)


@internal_router.post("/money-flow/{symbol}/collect", dependencies=[Depends(require_admin)])
def collect_money_flow(symbol: str, db: Session = Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    from app.qmr_exit.money_flow import MoomooMoneyFlowProvider
    row, created = QmrExitService(db, settings).collect_money_flow(symbol, MoomooMoneyFlowProvider())
    return {"id": row.id, "symbol": row.symbol, "created": created,
            "data_available": row.data_available, "money_flow_regime": row.money_flow_regime}
