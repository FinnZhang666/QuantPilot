from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.backup import BackupService
from app.config.settings import Settings, get_settings
from app.dashboard.auth import require_admin, require_read
from app.database.session import get_db
from app.platform.environment import validate_environment
from app.platform.health import health_report, runtime_diagnostics
from app.version import version_info

router = APIRouter(prefix="/api/platform", tags=["平台基础"])


@router.get("/health", dependencies=[Depends(require_read)])
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return health_report(db, settings)


@router.get("/runtime", dependencies=[Depends(require_read)])
def runtime(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return runtime_diagnostics(db, settings)


@router.get("/version", dependencies=[Depends(require_read)])
def version(db: Session = Depends(get_db)):
    return version_info(db)


@router.get("/config", dependencies=[Depends(require_admin)])
def config(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return {
        "configuration": settings.safe_dict(),
        "environment": validate_environment(settings, db),
        "secrets": {
            "telegram_bot_token": "******" if settings.telegram_bot_token else "",
            "dashboard_admin_token": "******" if settings.dashboard_admin_token else "",
            "ai_review_api_key": "******" if settings.ai_review_api_key else "",
        },
    }


@router.get("/backups", dependencies=[Depends(require_admin)])
def backups(settings: Settings = Depends(get_settings)):
    return {"items": BackupService(settings).list()}


@router.post("/backups", dependencies=[Depends(require_admin)])
def create_backup(backup_type: str = "manual", settings: Settings = Depends(get_settings)):
    try:
        return BackupService(settings).create(backup_type)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
