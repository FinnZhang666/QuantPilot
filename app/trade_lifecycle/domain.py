from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional


class LifecycleStage(str, Enum):
    DISCOVER = "DISCOVER"
    PLAN = "PLAN"
    COMPANION = "COMPANION"
    REVIEW = "REVIEW"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradePlanStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


ALLOWED_TRANSITIONS = {
    LifecycleStage.DISCOVER: {
        LifecycleStage.PLAN, LifecycleStage.CANCELLED, LifecycleStage.EXPIRED,
    },
    LifecycleStage.PLAN: {
        LifecycleStage.COMPANION, LifecycleStage.CANCELLED, LifecycleStage.EXPIRED,
    },
    LifecycleStage.COMPANION: {
        LifecycleStage.REVIEW, LifecycleStage.CANCELLED, LifecycleStage.EXPIRED,
    },
    LifecycleStage.REVIEW: set(),
    LifecycleStage.CANCELLED: set(),
    LifecycleStage.EXPIRED: set(),
}


@dataclass(frozen=True)
class TradePlanDraft:
    symbol: str
    market: str
    strategy_name: str
    strategy_version: str
    direction: TradeDirection
    timeframe: str
    signal_id: Optional[int] = None
    reference_price: Optional[Decimal] = None
    buy_zone_lower: Optional[Decimal] = None
    buy_zone_upper: Optional[Decimal] = None
    trend_add_on_zone_lower: Optional[Decimal] = None
    trend_add_on_zone_upper: Optional[Decimal] = None
    breakout_zone_lower: Optional[Decimal] = None
    breakout_zone_upper: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None
    target_prices: List[str] = field(default_factory=list)
    invalidation_condition: Optional[str] = None
    confidence: Optional[int] = None
    score: Optional[int] = None
    source_metadata: Dict[str, object] = field(default_factory=dict)


def normalize_stage(value) -> LifecycleStage:
    try:
        return value if isinstance(value, LifecycleStage) else LifecycleStage(str(value).upper())
    except ValueError:
        raise ValueError("生命周期阶段无效：%s" % value)


def normalize_direction(value) -> TradeDirection:
    try:
        return value if isinstance(value, TradeDirection) else TradeDirection(str(value).upper())
    except ValueError:
        raise ValueError("Trade Plan方向必须是LONG或SHORT。")
