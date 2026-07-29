from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class MarketRegimeResult:
    regime: str
    trend_score: int
    breadth_score: Optional[int]
    momentum_score: int
    volatility_score: int
    risk_score: int
    long_bias: int
    short_bias: int
    confidence: int
    bar_time: datetime
    features: Dict[str, object]
    reasons: List[str]
    risks: List[str]
    data_sufficient: bool
    config_version: str
