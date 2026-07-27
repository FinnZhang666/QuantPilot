import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from app.core.enums import BarInterval
from app.historical.timezone import NEW_YORK, SHANGHAI, market_time_to_utc
from app.realtime.models import RealtimeBarData, RealtimeQuoteData, RealtimeTickerData
from app.realtime.session import MarketSessionStateMachine


def decimal_value(value: Any, required: bool = False) -> Optional[Decimal]:
    if value is None or str(value).lower() in {"", "none", "nan", "n/a"}:
        if required:
            raise ValueError("缺少必需的价格字段")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        if required:
            raise ValueError("价格字段无法转换为Decimal")
        return None


def integer_value(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def records(data: Any) -> List[Dict[str, Any]]:
    if hasattr(data, "to_dict"):
        return list(data.to_dict("records"))
    return list(data or [])


def parse_market_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=NEW_YORK).astimezone(timezone.utc)
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc)
        return parsed.replace(tzinfo=NEW_YORK).astimezone(timezone.utc)
    except ValueError:
        return market_time_to_utc(text)


def row_market_time(row: Dict[str, Any], *keys: str) -> datetime:
    for key in keys:
        value = row.get(key)
        if value:
            text = str(value)
            if " " not in text and ":" in text and row.get("data_date"):
                text = str(row["data_date"]) + " " + text
            return parse_market_time(text)
    raise ValueError("行情数据缺少时间字段")


class MoomooRealtimeNormalizer:
    def __init__(self, session_engine: Optional[MarketSessionStateMachine] = None):
        self.session_engine = session_engine or MarketSessionStateMachine()

    def quotes(self, data: Any) -> List[RealtimeQuoteData]:
        result = []
        for row in records(data):
            timestamp = row_market_time(row, "data_time", "time", "update_time")
            market_time = timestamp.astimezone(NEW_YORK)
            session = self.session_engine.update(timestamp, row.get("market_state")).session
            result.append(RealtimeQuoteData(
                symbol=str(row.get("code", "")).upper(),
                timestamp_utc=timestamp,
                timestamp_market=market_time,
                timestamp_beijing=timestamp.astimezone(SHANGHAI),
                last_price=decimal_value(row.get("last_price"), True),
                open_price=decimal_value(row.get("open_price")),
                high_price=decimal_value(row.get("high_price")),
                low_price=decimal_value(row.get("low_price")),
                prev_close=decimal_value(row.get("prev_close_price") or row.get("prev_close")),
                volume=integer_value(row.get("volume")),
                turnover=decimal_value(row.get("turnover")),
                amplitude=decimal_value(row.get("amplitude")),
                turnover_rate=decimal_value(row.get("turnover_rate")),
                bid_price=decimal_value(row.get("bid_price")),
                ask_price=decimal_value(row.get("ask_price")),
                bid_volume=integer_value(row.get("bid_vol") or row.get("bid_volume")),
                ask_volume=integer_value(row.get("ask_vol") or row.get("ask_volume")),
                market_session=session,
                market_status=str(row.get("market_state", "")) or None,
            ))
        return result

    def tickers(self, data: Any) -> List[RealtimeTickerData]:
        result = []
        for row in records(data):
            timestamp = row_market_time(row, "time", "ticker_time")
            symbol = str(row.get("code", "")).upper()
            price = decimal_value(row.get("price"), True)
            volume = integer_value(row.get("volume"), 0) or 0
            sequence = str(row.get("sequence") or row.get("sequence_id") or "")
            if not sequence:
                raw = "%s|%s|%s|%s" % (symbol, timestamp.isoformat(), price, volume)
                sequence = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
            result.append(RealtimeTickerData(
                symbol=symbol,
                ticker_time_utc=timestamp,
                ticker_time_market=timestamp.astimezone(NEW_YORK),
                price=price,
                volume=volume,
                turnover=decimal_value(row.get("turnover")),
                direction=str(row.get("ticker_direction") or row.get("direction") or "") or None,
                sequence=sequence,
                market_session=self.session_engine.update(timestamp).session,
            ))
        return result

    def bars(self, data: Any) -> List[RealtimeBarData]:
        result = []
        for row in records(data):
            timestamp = row_market_time(row, "time_key", "time")
            market_time = timestamp.astimezone(NEW_YORK)
            is_closed_value = row.get("is_closed")
            is_closed = (
                bool(is_closed_value)
                if is_closed_value is not None
                else datetime.now(timezone.utc) >= timestamp + timedelta(minutes=1)
            )
            result.append(RealtimeBarData(
                symbol=str(row.get("code", "")).upper(),
                interval=BarInterval.MIN_1,
                timestamp_utc=timestamp,
                timestamp_market=market_time,
                trading_date=market_time.date().isoformat(),
                open=decimal_value(row.get("open"), True),
                high=decimal_value(row.get("high"), True),
                low=decimal_value(row.get("low"), True),
                close=decimal_value(row.get("close"), True),
                volume=integer_value(row.get("volume"), 0) or 0,
                turnover=decimal_value(row.get("turnover")),
                is_closed=is_closed,
                market_session=self.session_engine.update(timestamp).session,
            ))
        return result
