from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class StrategyInput:
    symbol: str
    market: str
    timeframe: str
    bar_timestamp: datetime
    enabled: bool
    role: str
    validation_status: str
    benchmark_symbol: str
    parameters: Dict[str, object]
    parameters_hash: str
    features: Dict[str, Optional[Decimal]]
    feature_statuses: Dict[str, str]
    feature_refs: Dict[str, dict]


@dataclass
class SignalEvaluation:
    signal_type: str
    score: int
    confidence: int
    status: str
    summary_zh: str
    reasons: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    feature_refs: Dict[str, dict] = field(default_factory=dict)
    components: Dict[str, int] = field(default_factory=dict)
