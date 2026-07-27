from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db

router = APIRouter()


@router.get("/health")
def health(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    database = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "disconnected"
    return {
        "status": "ok" if database == "connected" else "degraded",
        "environment": settings.app_env,
        "database": database,
        "trading_mode": settings.trading_mode.value,
        "live_trading": "blocked",
    }
