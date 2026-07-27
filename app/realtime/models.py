from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set

from app.core.enums import BarInterval, MarketSession, RealtimeDataType


@dataclass
class RealtimeQuoteData:
    symbol: str
    timestamp_utc: datetime
    timestamp_market: datetime
    timestamp_beijing: datetime
    last_price: Decimal
    open_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    prev_close: Optional[Decimal] = None
    volume: Optional[int] = None
    turnover: Optional[Decimal] = None
    amplitude: Optional[Decimal] = None
    turnover_rate: Optional[Decimal] = None
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    bid_volume: Optional[int] = None
    ask_volume: Optional[int] = None
    market_session: MarketSession = MarketSession.UNKNOWN
    market_status: Optional[str] = None
    data_source: str = "MOOMOO"


@dataclass
class RealtimeTickerData:
    symbol: str
    ticker_time_utc: datetime
    ticker_time_market: datetime
    price: Decimal
    volume: int
    turnover: Optional[Decimal] = None
    direction: Optional[str] = None
    sequence: str = ""
    market_session: MarketSession = MarketSession.UNKNOWN
    data_source: str = "MOOMOO"


@dataclass
class RealtimeBarData:
    symbol: str
    interval: BarInterval
    timestamp_utc: datetime
    timestamp_market: datetime
    trading_date: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    turnover: Optional[Decimal] = None
    is_closed: bool = False
    market_session: MarketSession = MarketSession.UNKNOWN
    data_source: str = "MOOMOO"


@dataclass
class SubscriptionResult:
    successful: Dict[str, List[str]] = field(default_factory=dict)
    failed: Dict[str, Dict[str, str]] = field(default_factory=dict)
    skipped: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class MarketSessionResult:
    session: MarketSession
    session_text: str
    source: str
    confidence: str
    reason: str
    next_expected_transition: Optional[datetime]


@dataclass
class RealtimeHealthReport:
    status: str
    opend_connected: bool
    current_session: MarketSession
    subscribed_symbol_count: int
    subscribed_types: Set[RealtimeDataType]
    queue_size: int
    queue_capacity: int
    received_count: int
    persisted_count: int
    duplicate_count: int
    dropped_count: int
    error_count: int
    reconnect_count: int
    last_message_at: Optional[datetime]
    warnings: List[str] = field(default_factory=list)

