"""One safe error vocabulary shared by data, strategy, Agent and execution."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    OPEND_DISCONNECTED = "OPEND_DISCONNECTED"
    OPEND_TIMEOUT = "OPEND_TIMEOUT"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DATA_STALE = "DATA_STALE"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    STALE_DATA = "DATA_STALE"
    INCOMPLETE_DATA = "DATA_INCOMPLETE"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    SYMBOL_UNSUPPORTED = "SYMBOL_UNSUPPORTED"
    QUOTE_PERMISSION_DENIED = "QUOTE_PERMISSION_DENIED"
    TRADE_PERMISSION_DENIED = "TRADE_PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    DATABASE_ERROR = "DATABASE_ERROR"
    CACHE_ERROR = "CACHE_ERROR"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_TIMEOUT = "ORDER_TIMEOUT"
    ORDER_DUPLICATE = "ORDER_DUPLICATE"
    INVALID_POSITION = "INVALID_POSITION"
    MARKET_CLOSED = "MARKET_CLOSED"
    SESSION_NOT_EXECUTABLE = "SESSION_NOT_EXECUTABLE"
    PAPER_ACCOUNT_UNAVAILABLE = "PAPER_ACCOUNT_UNAVAILABLE"
    REAL_TRADING_BLOCKED = "REAL_TRADING_BLOCKED"
    INTERNAL_CALCULATION_ERROR = "INTERNAL_CALCULATION_ERROR"


ERROR_ACTIONS = {
    ErrorCode.DATA_STALE: "BLOCK_ENTRY",
    ErrorCode.DATA_INCOMPLETE: "BLOCK_ENTRY",
    ErrorCode.DATA_UNAVAILABLE: "BLOCK_ENTRY",
    ErrorCode.OPEND_DISCONNECTED: "ALLOW_EXIT_ONLY",
    ErrorCode.OPEND_TIMEOUT: "RETRY",
    ErrorCode.RATE_LIMITED: "RETRY",
    ErrorCode.ORDER_REJECTED: "FAIL",
    ErrorCode.REAL_TRADING_BLOCKED: "FAIL",
    ErrorCode.QUOTE_PERMISSION_DENIED: "WARN",
}


USER_MESSAGES_ZH = {
    ErrorCode.OPEND_DISCONNECTED: "OpenD当前未连接，本次不会使用旧数据生成买入结论。",
    ErrorCode.OPEND_TIMEOUT: "行情服务暂时超时，请稍后重试。",
    ErrorCode.DATA_UNAVAILABLE: "当前没有足够数据。",
    ErrorCode.DATA_STALE: "行情数据已经过期，本次不会使用旧数据生成买入结论。",
    ErrorCode.DATA_INCOMPLETE: "数据不完整，暂时无法形成可靠结论。",
    ErrorCode.SYMBOL_NOT_FOUND: "未找到该标的，请检查代码或名称。",
    ErrorCode.SYMBOL_UNSUPPORTED: "当前数据层暂不支持该标的。",
    ErrorCode.QUOTE_PERMISSION_DENIED: "当前账户没有该行情的读取权限。",
    ErrorCode.ORDER_REJECTED: "模拟订单未被接受，系统不会显示为已成交。",
    ErrorCode.PAPER_ACCOUNT_UNAVAILABLE: "无法确认模拟账户，已安全阻止执行。",
    ErrorCode.REAL_TRADING_BLOCKED: "真实交易已被系统安全策略禁止。",
}


@dataclass(frozen=True)
class AppError:
    error_code: ErrorCode
    source: str
    message: str
    symbol: Optional[str] = None
    timestamp: datetime = None
    retryable: bool = False
    severity: str = "error"
    raw_error_optional: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc))

    @property
    def action(self):
        return ERROR_ACTIONS.get(self.error_code, "FAIL")

    def user_message(self, language="zh-CN"):
        if language == "zh-CN":
            return USER_MESSAGES_ZH.get(self.error_code, "服务暂时不可用，请稍后重试。")
        return self.message

    def safe_dict(self):
        value = asdict(self)
        value["error_code"] = self.error_code.value
        value["timestamp"] = self.timestamp.isoformat()
        value.pop("raw_error_optional", None)
        value["action"] = self.action
        return value


class ControlledServiceError(RuntimeError):
    def __init__(self, error: AppError):
        super().__init__(error.message)
        self.error = error


def map_exception(exc, source, symbol=None):
    text = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in text:
        code, retryable = ErrorCode.OPEND_TIMEOUT, True
    elif "permission" in text or "no right" in text:
        code, retryable = ErrorCode.QUOTE_PERMISSION_DENIED, False
    elif "rate" in text and "limit" in text:
        code, retryable = ErrorCode.RATE_LIMITED, True
    elif "database" in text or "sqlite" in text:
        code, retryable = ErrorCode.DATABASE_ERROR, True
    else:
        code, retryable = ErrorCode.DATA_UNAVAILABLE, True
    return AppError(code, source, type(exc).__name__, symbol=symbol,
                    retryable=retryable, severity="warning",
                    raw_error_optional=type(exc).__name__)
