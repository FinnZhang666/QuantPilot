from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class UniverseSymbol:
    symbol: str
    market: str = "US"
    asset_type: str = "UNKNOWN"
    source: str = "SYSTEM"
    sector: Optional[str] = None
    benchmark: Optional[str] = None


@dataclass
class FilterResult:
    name: str
    passed: bool
    long_score_delta: int
    short_score_delta: int
    reasons: List[str]
    risks: List[str]
    data_sufficient: bool
    snapshot: Dict[str, object]
