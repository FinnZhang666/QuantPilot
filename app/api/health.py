from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.database.models import SystemPaperAccount
from app.database.session import get_db
from app.api.local_node import market_context
from app.platform.health import health_report, runtime_diagnostics

router = APIRouter(tags=["平台健康"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    report = health_report(db, settings)
    context = market_context(db)
    paper = db.query(SystemPaperAccount).filter(SystemPaperAccount.account_key == "system-paper").first()
    report["components"] = {
        "database": "HEALTHY" if report["database"]["status"] == "OK" else "OFFLINE",
        "opend": context["opend"],
        "market_data_freshness": context["market_data_freshness"],
        "scheduler": "HEALTHY" if report["scheduler"] in {"RUNNING", "CONNECTED"} else "DEGRADED",
        "telegram": "HEALTHY" if report["telegram"] == "RUNNING" else "DEGRADED",
        "paper_adapter": "HEALTHY" if paper is not None else "DEGRADED",
        "local_api": "HEALTHY",
        "real_trading": "OFFLINE",
    }
    return report


@router.get("/runtime")
def runtime(settings: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    return runtime_diagnostics(db, settings)
