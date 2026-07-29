import os
import resource
import shutil
from pathlib import Path

from sqlalchemy import func, select, text

from app.database.models import AIReviewAnalysis, Opportunity, RuntimeStatus
from app.database.models import OpportunityReview
from app.platform.environment import validate_environment
from app.version import version_info


def health_report(db, settings):
    database = "OK"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "ERROR"
    services = {
        row.service_name: row.status
        for row in db.scalars(select(RuntimeStatus))
    }
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    usage = shutil.disk_usage(db_path.parent)
    environment = validate_environment(settings, db)
    statuses = [
        database,
        "WARNING" if environment["status"] == "WARNING" else environment["status"],
    ]
    overall = "ERROR" if "ERROR" in statuses or "FAILED" in statuses else (
        "WARNING" if "WARNING" in statuses else "OK"
    )
    memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if os.uname().sysname == "Darwin":
        memory_mb = memory_mb / 1024 ** 2
    else:
        memory_mb = memory_mb / 1024
    return {
        "status": overall,
        "trading_mode": settings.trading_mode.value,
        "live_trading": "blocked",
        "environment_name": settings.app_env,
        "application": "OK",
        "version": version_info(db),
        "database": {"status": database, "path": str(db_path), "size_bytes": db_path.stat().st_size if db_path.exists() else 0},
        "runtime": services.get("realtime_runtime", "STOPPED"),
        "telegram": services.get("telegram", "DISABLED" if not settings.telegram_enabled else "UNKNOWN"),
        "ai": services.get("ai_review_analyst", "DISABLED" if not settings.ai_review_enabled else "UNKNOWN"),
        "scheduler": services.get("opportunity_pipeline", "UNKNOWN"),
        "disk": {"free_gb": round(usage.free / 1024 ** 3, 2), "total_gb": round(usage.total / 1024 ** 3, 2)},
        "memory": {"process_mb": round(memory_mb, 2)},
        "python": version_info()["python"],
        "environment": environment,
    }


def runtime_diagnostics(db, settings):
    report = health_report(db, settings)
    report.update({
        "runtime_thread": report["runtime"],
        "pending_opportunities": db.scalar(select(func.count()).select_from(Opportunity).where(
            Opportunity.status.in_(["DETECTED", "NOTIFIED", "ACTIVE"]),
        )) or 0,
        "pending_reviews": db.scalar(select(func.count()).select_from(Opportunity).where(
            Opportunity.status.in_(["EXPIRED", "REVIEW_PENDING"]),
        )) or 0,
        "pending_ai": db.scalar(select(func.count()).select_from(AIReviewAnalysis).where(
            AIReviewAnalysis.status.in_(["PENDING", "RUNNING"]),
        )) or 0,
        "review_records": db.scalar(select(func.count()).select_from(OpportunityReview)) or 0,
        "cpu_load": list(os.getloadavg()) if hasattr(os, "getloadavg") else [],
        "queue": {"status": "internal", "external_queue": False},
    })
    return report
