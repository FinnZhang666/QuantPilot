from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import RuntimeStatus
from app.database.session import get_db
from app.runtime.realtime_runtime import get_runtime

router = APIRouter(prefix="/api/runtime", tags=["实时Runtime"])


@router.get("/status")
def runtime_status(db: Session = Depends(get_db)):
    rows = db.scalars(select(RuntimeStatus).order_by(RuntimeStatus.service_name)).all()
    live = get_runtime().snapshot()
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


@router.post("/start")
def start_runtime():
    return get_runtime().start()


@router.post("/stop")
def stop_runtime():
    return get_runtime().stop()
