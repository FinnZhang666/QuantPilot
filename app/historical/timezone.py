from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.core.enums import MarketSession

UTC = ZoneInfo("UTC")
NEW_YORK = ZoneInfo("America/New_York")
SHANGHAI = ZoneInfo("Asia/Shanghai")


def market_time_to_utc(value: str) -> datetime:
    naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=NEW_YORK).astimezone(UTC)


def classify_us_session(value: datetime) -> MarketSession:
    market_time = value.astimezone(NEW_YORK)
    if market_time.weekday() >= 5:
        return MarketSession.CLOSED
    clock = market_time.time()
    if time(4, 0) <= clock < time(9, 30):
        return MarketSession.PRE_MARKET
    if time(9, 30) <= clock < time(16, 0):
        return MarketSession.REGULAR
    if time(16, 0) <= clock < time(20, 0):
        return MarketSession.AFTER_HOURS
    if clock >= time(20, 0) or clock < time(4, 0):
        return MarketSession.OVERNIGHT
    return MarketSession.UNKNOWN
