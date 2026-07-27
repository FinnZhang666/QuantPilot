from enum import Enum


class TradingMode(str, Enum):
    INTERNAL_PAPER = "INTERNAL_PAPER"
    MOOMOO_PAPER = "MOOMOO_PAPER"
    LIVE = "LIVE"


class MarketSession(str, Enum):
    OVERNIGHT = "OVERNIGHT"
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class BarInterval(str, Enum):
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    HOUR_1 = "60m"
    DAY_1 = "1d"


class AdjustmentType(str, Enum):
    NONE = "NONE"
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"


class HistoryJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class HistoryErrorCode(str, Enum):
    OPEND_UNREACHABLE = "OPEND_UNREACHABLE"
    OPEND_NOT_LOGGED_IN = "OPEND_NOT_LOGGED_IN"
    SDK_ERROR = "SDK_ERROR"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    UNSUPPORTED_SECURITY = "UNSUPPORTED_SECURITY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    EMPTY_RESULT = "EMPTY_RESULT"
    PAGINATION_ERROR = "PAGINATION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class RealtimeDataType(str, Enum):
    QUOTE = "QUOTE"
    TICKER = "TICKER"
    KLINE_1M = "KLINE_1M"
    MARKET_STATE = "MARKET_STATE"


class RealtimeServiceState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    FAILED = "FAILED"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
