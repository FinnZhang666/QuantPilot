from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import RuntimeStatus


class RuntimeStateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, service_name: str) -> RuntimeStatus:
        row = self.db.scalar(select(RuntimeStatus).where(RuntimeStatus.service_name == service_name))
        if row is None:
            row = RuntimeStatus(service_name=service_name, status="STOPPED", metadata_json={})
            self.db.add(row)
            self.db.commit()
        return row

    def update(
        self, service_name: str, status: str, metadata: Optional[Dict[str, object]] = None,
        error: Optional[str] = None, success: bool = False,
    ) -> RuntimeStatus:
        row = self.get(service_name)
        now = datetime.now(timezone.utc)
        row.status = status
        row.last_heartbeat_at = now
        if success:
            row.last_success_at = now
        if error:
            row.last_error_at = now
            row.last_error_message = error[:2000]
        if metadata is not None:
            row.metadata_json = metadata
        self.db.commit()
        return row
