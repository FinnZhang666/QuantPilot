from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class HoldingRecord:
    symbol: str
    company_name: Optional[str] = None
    weight: Optional[Decimal] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[Decimal] = None


@dataclass(frozen=True)
class UniverseSource:
    fund_symbol: str
    provider: str
    url: str
    file_format: str
    parser: str
    enabled: bool = True
    role: str = "PRIMARY"
    source_type: str = "HTTP_FILE"
    priority: int = 100


@dataclass(frozen=True)
class UniverseSnapshot:
    universe_code: str
    source_name: str
    source_type: str
    members: List[HoldingRecord]
    fetched_at: datetime
    effective_at: datetime


@dataclass(frozen=True)
class UniverseFetchResult:
    universe_code: str
    source_name: str
    source_type: str
    members: List[HoldingRecord]
    fetched_at: datetime
    effective_at: datetime
    data_available: bool
    freshness: str
    quality: str
    fallback_used: bool = False
    cache_used: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None
