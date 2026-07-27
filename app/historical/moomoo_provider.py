import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional

from app.core.enums import AdjustmentType, BarInterval, HistoryErrorCode, MarketSession
from app.data.providers.moomoo import MoomooConnectionManager
from app.historical.base import HistoricalDataProvider
from app.historical.models import ERROR_TEXT_ZH, HistoryFetchResult, MarketBarData
from app.historical.timezone import NEW_YORK, classify_us_session, market_time_to_utc


def decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None or str(value).lower() in {"nan", "none", ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def classify_sdk_error(message: Any) -> HistoryErrorCode:
    text = str(message).lower()
    if "permission" in text or "no right" in text or "权限" in text:
        return HistoryErrorCode.PERMISSION_DENIED
    if "frequency" in text or "rate" in text or "频繁" in text:
        return HistoryErrorCode.RATE_LIMITED
    if "code" in text or "symbol" in text or "股票" in text:
        return HistoryErrorCode.INVALID_SYMBOL
    if "login" in text or "登录" in text:
        return HistoryErrorCode.OPEND_NOT_LOGGED_IN
    return HistoryErrorCode.SDK_ERROR


class MoomooHistoricalDataProvider(HistoricalDataProvider):
    def __init__(
        self,
        manager: MoomooConnectionManager,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
        request_interval_seconds: float = 0.3,
        max_pages: int = 500,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.manager = manager
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.request_interval_seconds = request_interval_seconds
        self.max_pages = max_pages
        self.sleep = sleep

    @staticmethod
    def interval_map(sdk: Any) -> Dict[BarInterval, Any]:
        return {
            BarInterval.MIN_1: sdk.KLType.K_1M,
            BarInterval.MIN_5: sdk.KLType.K_5M,
            BarInterval.MIN_15: sdk.KLType.K_15M,
            BarInterval.MIN_30: sdk.KLType.K_30M,
            BarInterval.HOUR_1: sdk.KLType.K_60M,
            BarInterval.DAY_1: sdk.KLType.K_DAY,
        }

    @staticmethod
    def adjustment_map(sdk: Any) -> Dict[AdjustmentType, Any]:
        return {
            AdjustmentType.NONE: sdk.AuType.NONE,
            AdjustmentType.FORWARD: sdk.AuType.QFQ,
            AdjustmentType.BACKWARD: sdk.AuType.HFQ,
        }

    def normalize_rows(
        self,
        rows: Any,
        symbol: str,
        interval: BarInterval,
        adjustment_type: AdjustmentType,
    ) -> List[MarketBarData]:
        records = rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows or [])
        bars: List[MarketBarData] = []
        for row in records:
            timestamp_utc = market_time_to_utc(str(row["time_key"]))
            timestamp_market = timestamp_utc.astimezone(NEW_YORK)
            session = (
                MarketSession.REGULAR
                if interval == BarInterval.DAY_1
                else classify_us_session(timestamp_market)
            )
            bars.append(
                MarketBarData(
                    symbol=symbol,
                    interval=interval,
                    timestamp_utc=timestamp_utc,
                    timestamp_market=timestamp_market,
                    trading_date=timestamp_market.date(),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=int(row.get("volume", 0)),
                    turnover=decimal_or_none(row.get("turnover")),
                    change_rate=decimal_or_none(row.get("change_rate")),
                    last_close=decimal_or_none(row.get("last_close")),
                    is_blank=bool(row.get("is_blank", False)),
                    market_session=session,
                    adjustment_type=adjustment_type,
                )
            )
        return bars

    def fetch_bars(
        self,
        symbol: str,
        interval: BarInterval,
        start_time: datetime,
        end_time: datetime,
        adjustment_type: AdjustmentType,
    ) -> HistoryFetchResult:
        result = HistoryFetchResult(symbol=symbol, interval=interval)
        if start_time.tzinfo is None or end_time.tzinfo is None or start_time >= end_time:
            result.error_code = HistoryErrorCode.VALIDATION_ERROR
            result.error_message_zh = ERROR_TEXT_ZH[result.error_code]
            return result
        socket_result = self.manager.check_opend_socket()
        if not socket_result.success:
            result.error_code = HistoryErrorCode.OPEND_UNREACHABLE
            result.error_message_zh = ERROR_TEXT_ZH[result.error_code]
            return result
        context = None
        seen_tokens = set()
        token = None
        try:
            sdk = self.manager._sdk()
            context = self.manager.open_quote_context()
            while True:
                if result.pages_requested >= self.max_pages:
                    result.error_code = HistoryErrorCode.PAGINATION_ERROR
                    result.error_message_zh = "已达到最大分页数，停止请求"
                    break
                response = None
                for attempt in range(self.max_retries + 1):
                    response = context.request_history_kline(
                        symbol,
                        start=start_time.astimezone(NEW_YORK).strftime("%Y-%m-%d"),
                        end=end_time.astimezone(NEW_YORK).strftime("%Y-%m-%d"),
                        ktype=self.interval_map(sdk)[interval],
                        autype=self.adjustment_map(sdk)[adjustment_type],
                        max_count=1000,
                        page_req_key=token,
                        extended_time=interval != BarInterval.DAY_1,
                        session=sdk.Session.ALL,
                    )
                    ret, data, next_token = response
                    if ret == sdk.RET_OK:
                        break
                    code = classify_sdk_error(data)
                    if code in {
                        HistoryErrorCode.PERMISSION_DENIED,
                        HistoryErrorCode.INVALID_SYMBOL,
                    } or attempt >= self.max_retries:
                        result.error_code = code
                        result.error_message_zh = ERROR_TEXT_ZH[code]
                        return result
                    self.sleep(self.retry_delay_seconds * (2 ** attempt))
                result.pages_requested += 1
                result.bars.extend(
                    self.normalize_rows(data, symbol, interval, adjustment_type)
                )
                if next_token is None:
                    break
                token_key = bytes(next_token) if isinstance(next_token, bytearray) else str(next_token)
                if token_key in seen_tokens:
                    result.error_code = HistoryErrorCode.PAGINATION_ERROR
                    result.error_message_zh = "检测到重复分页Token，已停止请求"
                    break
                seen_tokens.add(token_key)
                token = next_token
                if self.request_interval_seconds:
                    self.sleep(self.request_interval_seconds)
            if not result.bars and result.error_code is None:
                result.error_code = HistoryErrorCode.EMPTY_RESULT
                result.error_message_zh = ERROR_TEXT_ZH[result.error_code]
        except TimeoutError:
            result.error_code = HistoryErrorCode.TIMEOUT
            result.error_message_zh = ERROR_TEXT_ZH[result.error_code]
        except Exception as exc:
            result.error_code = HistoryErrorCode.SDK_ERROR
            result.error_message_zh = ERROR_TEXT_ZH[result.error_code] + "：" + type(exc).__name__
        finally:
            self.manager.close_all()
        return result
