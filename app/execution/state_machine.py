from enum import Enum

from app.core.errors import AppError, ControlledServiceError, ErrorCode


class CanonicalOrderStatus(str, Enum):
    PENDING_EXECUTION = "PENDING_EXECUTION"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


TERMINAL = frozenset({
    CanonicalOrderStatus.FILLED, CanonicalOrderStatus.CANCELLED,
    CanonicalOrderStatus.REJECTED, CanonicalOrderStatus.FAILED,
})

ALLOWED_TRANSITIONS = {
    CanonicalOrderStatus.PENDING_EXECUTION: {
        CanonicalOrderStatus.SUBMITTED, CanonicalOrderStatus.CANCELLED,
        CanonicalOrderStatus.REJECTED, CanonicalOrderStatus.FAILED,
    },
    CanonicalOrderStatus.SUBMITTED: {
        CanonicalOrderStatus.PARTIALLY_FILLED, CanonicalOrderStatus.FILLED,
        CanonicalOrderStatus.CANCELLED, CanonicalOrderStatus.REJECTED,
        CanonicalOrderStatus.FAILED,
    },
    CanonicalOrderStatus.PARTIALLY_FILLED: {
        CanonicalOrderStatus.PARTIALLY_FILLED, CanonicalOrderStatus.FILLED,
        CanonicalOrderStatus.CANCELLED, CanonicalOrderStatus.FAILED,
    },
}

BROKER_STATUS_MAP = {
    "UNSUBMITTED": CanonicalOrderStatus.PENDING_EXECUTION,
    "WAITING_SUBMIT": CanonicalOrderStatus.PENDING_EXECUTION,
    "SUBMITTING": CanonicalOrderStatus.SUBMITTED,
    "SUBMITTED": CanonicalOrderStatus.SUBMITTED,
    "FILLED_PART": CanonicalOrderStatus.PARTIALLY_FILLED,
    "PARTIALLY_FILLED": CanonicalOrderStatus.PARTIALLY_FILLED,
    "FILLED_ALL": CanonicalOrderStatus.FILLED,
    "FILLED": CanonicalOrderStatus.FILLED,
    "CANCELLED_ALL": CanonicalOrderStatus.CANCELLED,
    "CANCELLED_PART": CanonicalOrderStatus.CANCELLED,
    "CANCELLED": CanonicalOrderStatus.CANCELLED,
    "FAILED": CanonicalOrderStatus.FAILED,
    "TIMEOUT": CanonicalOrderStatus.FAILED,
    "DISABLED": CanonicalOrderStatus.REJECTED,
    "DELETED": CanonicalOrderStatus.REJECTED,
    "REJECTED": CanonicalOrderStatus.REJECTED,
}


def normalize_broker_status(value):
    status = str(value or "").strip().upper()
    if status not in BROKER_STATUS_MAP:
        raise ControlledServiceError(AppError(
            ErrorCode.ORDER_REJECTED, "order_state_machine",
            "Unknown broker order status: %s" % status))
    return BROKER_STATUS_MAP[status]


def validate_transition(current, target):
    current = current if isinstance(current, CanonicalOrderStatus) else CanonicalOrderStatus(current)
    target = target if isinstance(target, CanonicalOrderStatus) else CanonicalOrderStatus(target)
    if current == target:
        return target
    if current in TERMINAL or target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ControlledServiceError(AppError(
            ErrorCode.ORDER_REJECTED, "order_state_machine",
            "Illegal order transition %s -> %s" % (current.value, target.value)))
    return target
