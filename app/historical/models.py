from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.core.enums import AdjustmentType, BarInterval, HistoryErrorCode, MarketSession


@dataclass
class MarketBarData:
    symbol: str
    interval: BarInterval
    timestamp_utc: datetime
    timestamp_market: datetime
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    turnover: Optional[Decimal]
    change_rate: Optional[Decimal]
    last_close: Optional[Decimal]
    is_blank: bool
    market_session: MarketSession
    adjustment_type: AdjustmentType
    data_source: str = "MOOMOO"

    def validation_errors(self) -> List[str]:
        errors: List[str] = []
        if not self.symbol:
            errors.append("证券代码缺失")
        if self.timestamp_utc.tzinfo is None or self.timestamp_market.tzinfo is None:
            errors.append("时间戳缺少时区")
        if min(self.open, self.high, self.low, self.close) < 0:
            errors.append("价格不能为负数")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            errors.append("OHLC关系无效")
        if self.high < self.low:
            errors.append("最高价低于最低价")
        if self.volume < 0:
            errors.append("成交量不能为负数")
        return errors


@dataclass
class HistoryFetchResult:
    symbol: str
    interval: BarInterval
    bars: List[MarketBarData] = field(default_factory=list)
    pages_requested: int = 0
    error_code: Optional[HistoryErrorCode] = None
    error_message_zh: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.error_code is None

    def safe_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval": self.interval.value,
            "bars": len(self.bars),
            "pages_requested": self.pages_requested,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message_zh": self.error_message_zh,
            "warnings": self.warnings,
        }


ERROR_TEXT_ZH = {
    HistoryErrorCode.OPEND_UNREACHABLE: "OpenD不可达",
    HistoryErrorCode.OPEND_NOT_LOGGED_IN: "OpenD尚未登录",
    HistoryErrorCode.SDK_ERROR: "Moomoo SDK异常",
    HistoryErrorCode.INVALID_SYMBOL: "证券代码不存在或格式错误",
    HistoryErrorCode.UNSUPPORTED_SECURITY: "当前证券类型不支持",
    HistoryErrorCode.PERMISSION_DENIED: "行情权限不足",
    HistoryErrorCode.RATE_LIMITED: "请求频率受到限制",
    HistoryErrorCode.TIMEOUT: "请求超时",
    HistoryErrorCode.EMPTY_RESULT: "未返回历史行情",
    HistoryErrorCode.PAGINATION_ERROR: "历史行情分页异常",
    HistoryErrorCode.DATABASE_ERROR: "数据库写入失败",
    HistoryErrorCode.VALIDATION_ERROR: "历史行情数据校验失败",
    HistoryErrorCode.UNKNOWN_ERROR: "未知错误",
}
