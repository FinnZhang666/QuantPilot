from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import RuntimeStatus
from app.database.session import get_db
from app.runtime.realtime_runtime import get_runtime
from app.dashboard.auth import require_admin, require_read
from pathlib import Path
import json

router = APIRouter(prefix="/api/runtime", tags=["实时Runtime"])


@router.get("/status", dependencies=[Depends(require_read)])
def runtime_status(db: Session = Depends(get_db)):
    rows = db.scalars(select(RuntimeStatus).order_by(RuntimeStatus.service_name)).all()
    live = get_runtime().snapshot()
    pid_file = Path("data/opportunity_runtime.pid")
    runtime_pid = None
    if pid_file.exists():
        try:
            runtime_pid = json.loads(pid_file.read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError):
            runtime_pid = None
    live["pid"] = runtime_pid
    return {
        "runtime": live,
        "services": [
            {
                "service_name": row.service_name, "status": row.status,
                "last_heartbeat_at": row.last_heartbeat_at,
                "last_success_at": row.last_success_at,
                "last_error_at": row.last_error_at,
                "last_error_message": row.last_error_message,
                "metadata": row.metadata_json,
            }
            for row in rows
        ],
    }


@router.post("/start", dependencies=[Depends(require_admin)])
def start_runtime():
    return get_runtime().start()


@router.post("/stop", dependencies=[Depends(require_admin)])
def stop_runtime():
    return get_runtime().stop()
