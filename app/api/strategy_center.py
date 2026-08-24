from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.strategy.qmr_registry import StrategyCenterService


router = APIRouter(prefix="/api/strategy-center", tags=["策略中心"])
internal_router = APIRouter(prefix="/internal/strategy-center", include_in_schema=False)


@router.get("", dependencies=[Depends(require_read)])
def list_strategies(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    items = StrategyCenterService(db, settings).list()
    return {"items": items, "total": len(items)}


@router.get("/{strategy_code}", dependencies=[Depends(require_read)])
def get_strategy(strategy_code: str, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    try:
        return StrategyCenterService(db, settings).get(strategy_code)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))


@internal_router.post("/{strategy_code}/enable", dependencies=[Depends(require_admin)])
def enable_strategy(strategy_code: str, db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    try:
        return StrategyCenterService(db, settings).set_enabled(strategy_code, True)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))


@internal_router.post("/{strategy_code}/disable", dependencies=[Depends(require_admin)])
def disable_strategy(strategy_code: str, db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings)):
    try:
        return StrategyCenterService(db, settings).set_enabled(strategy_code, False)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'"))
