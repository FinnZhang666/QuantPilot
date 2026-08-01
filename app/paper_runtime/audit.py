from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database.models import SystemPaperAuditEvent


SENSITIVE_FRAGMENTS = (
    "token", "api_key", "apikey", "password", "cookie", "secret", "telegram",
    "broker_account", "account_id", ".env",
)


def sanitize_details(value: Any) -> Any:
    if isinstance(value, dict):
        clean: Dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in SENSITIVE_FRAGMENTS):
                continue
            clean[str(key)] = sanitize_details(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [sanitize_details(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if ".env" in lowered or "api key" in lowered or "authorization:" in lowered:
            return "[REDACTED]"
        return value[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2000]


class PaperAudit:
    """Append-only, non-secret lifecycle evidence for the system paper ledger."""

    def __init__(self, db: Session):
        self.db = db

    def record(
        self, event_type: str, *, candidate_id: Optional[int] = None,
        trade_plan_id: Optional[int] = None, order_id: Optional[int] = None,
        fill_id: Optional[int] = None, position_id: Optional[int] = None,
        review_id: Optional[int] = None, correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> SystemPaperAuditEvent:
        row = SystemPaperAuditEvent(
            event_type=event_type,
            candidate_id=candidate_id,
            trade_plan_id=trade_plan_id,
            order_id=order_id,
            fill_id=fill_id,
            position_id=position_id,
            review_id=review_id,
            correlation_id=correlation_id,
            details_json=sanitize_details(details or {}),
        )
        self.db.add(row)
        self.db.flush()
        return row
