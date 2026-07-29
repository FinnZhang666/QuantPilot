from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.database.session import get_db
from app.platform.health import health_report, runtime_diagnostics

router = APIRouter(tags=["平台健康"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    return health_report(db, settings)


@router.get("/runtime")
def runtime(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    return runtime_diagnostics(db, settings)
