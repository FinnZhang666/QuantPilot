from datetime import datetime, time, timedelta
from typing import Dict, Optional, Tuple

from app.core.enums import MarketSession
from app.historical.timezone import NEW_YORK
from app.realtime.models import MarketSessionResult

SESSION_TEXT = {
    MarketSession.OVERNIGHT: "夜盘行情",
    MarketSession.PRE_MARKET: "盘前",
    MarketSession.REGULAR: "正常盘",
    MarketSession.AFTER_HOURS: "盘后",
    MarketSession.CLOSED: "休市",
    MarketSession.UNKNOWN: "未知",
}

MOOMOO_STATE_MAP: Dict[str, MarketSession] = {
    "MORNING": MarketSession.REGULAR,
    "AFTERNOON": MarketSession.REGULAR,
    "PRE_MARKET_BEGIN": MarketSession.PRE_MARKET,
    "PRE_MARKET": MarketSession.PRE_MARKET,
    "AFTER_HOURS_BEGIN": MarketSession.AFTER_HOURS,
    "AFTER_HOURS": MarketSession.AFTER_HOURS,
    "CLOSED": MarketSession.CLOSED,
    "NONE": MarketSession.CLOSED,
}


class MarketSessionStateMachine:
    def __init__(self):
        self.current_session = MarketSession.UNKNOWN

    def update(
        self,
        current_time: datetime,
        moomoo_market_state: Optional[str] = None,
    ) -> MarketSessionResult:
        if current_time.tzinfo is None:
            return self._result(MarketSession.UNKNOWN, "UNKNOWN", "LOW", "时间缺少时区", None)
        market_time = current_time.astimezone(NEW_YORK)
        state = str(moomoo_market_state or "").upper()
        for key, session in MOOMOO_STATE_MAP.items():
            if key in state:
                return self._set(session, "MOOMOO_MARKET_STATE", "HIGH", "OpenD返回美股市场状态：" + state, None)
        if market_time.weekday() >= 5:
            return self._set(MarketSession.CLOSED, "WEEKEND_RULE", "HIGH", "美东时间为周末", None)
        value = market_time.time()
        session, next_time, reason = self._infer_time(market_time, value)
        confidence = "MEDIUM" if session == MarketSession.OVERNIGHT else "HIGH"
        return self._set(session, "TIME_INFERENCE", confidence, reason, next_time)

    def _infer_time(self, market_time: datetime, value: time) -> Tuple[MarketSession, datetime, str]:
        if time(4, 0) <= value < time(9, 30):
            return MarketSession.PRE_MARKET, market_time.replace(hour=9, minute=30, second=0, microsecond=0), "根据美东时间识别为盘前"
        if time(9, 30) <= value < time(16, 0):
            return MarketSession.REGULAR, market_time.replace(hour=16, minute=0, second=0, microsecond=0), "根据美东时间识别为正常盘"
        if time(16, 0) <= value < time(20, 0):
            return MarketSession.AFTER_HOURS, market_time.replace(hour=20, minute=0, second=0, microsecond=0), "根据美东时间识别为盘后"
        if value >= time(20, 0) or value < time(4, 0):
            next_day = market_time if value < time(4, 0) else market_time + timedelta(days=1)
            return MarketSession.OVERNIGHT, next_day.replace(hour=4, minute=0, second=0, microsecond=0), "根据美东时间推断为夜盘行情，未声明可交易"
        return MarketSession.UNKNOWN, market_time + timedelta(hours=1), "无法识别市场时段"

    def _set(self, session: MarketSession, source: str, confidence: str, reason: str, next_time: Optional[datetime]) -> MarketSessionResult:
        self.current_session = session
        return self._result(session, source, confidence, reason, next_time)

    @staticmethod
    def _result(session: MarketSession, source: str, confidence: str, reason: str, next_time: Optional[datetime]) -> MarketSessionResult:
        return MarketSessionResult(session, SESSION_TEXT[session], source, confidence, reason, next_time)

