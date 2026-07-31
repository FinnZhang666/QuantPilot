from dataclasses import dataclass
from typing import Dict, List, Optional

from app.market_snapshot.models import MarketSnapshot


@dataclass(frozen=True)
class SymbolOverview:
    symbol: str
    market: str
    snapshot: MarketSnapshot
    trade_plan: Optional[Dict[str, object]]
    holding: Optional[Dict[str, object]]
    review: Optional[Dict[str, object]]
    ai_analysis: Optional[Dict[str, object]]
    ai_history: List[Dict[str, object]]
    related_objects: Dict[str, Dict[str, object]]
