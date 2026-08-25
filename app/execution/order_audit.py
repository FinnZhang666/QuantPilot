from app.execution.state_machine import normalize_broker_status, validate_transition
from app.paper_runtime.audit import PaperAudit


class OrderStateAuditService:
    """Validate and append evidence for a broker status change.

    Persistence of the order itself remains owned by the existing Paper Runtime.
    """

    def __init__(self, db):
        self.audit = PaperAudit(db)

    def record_transition(self, order_id, previous_state, broker_status, reason=None):
        target = normalize_broker_status(broker_status)
        validate_transition(previous_state, target)
        return self.audit.record(
            "ORDER_STATE_CHANGED", order_id=order_id,
            details={"previous_state": str(getattr(previous_state, "value", previous_state)),
                     "new_state": target.value, "broker_status": str(broker_status),
                     "reason": reason})
