from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    market: str
    display_name: str
    latest_price: Optional[Decimal]
    latest_bar_time: Optional[datetime]
    strategy_status: str
    candidate_signal: str
    trade_plan_status: str
    holding: str
    holding_quantity: Optional[Decimal]
    average_cost: Optional[Decimal]
    watching: str
    feature_status: str
    updated_at: Optional[datetime]
    trade_plan_id: Optional[str] = None
    holding_id: Optional[int] = None
    portfolio_id: Optional[int] = None


def snapshot_dict(snapshot: MarketSnapshot):
    """Stable public representation shared by product integrations."""
    value = asdict(snapshot)
    for field in ("latest_price", "holding_quantity", "average_cost"):
        value[field] = str(value[field]) if value[field] is not None else None
    return value
