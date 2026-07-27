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
