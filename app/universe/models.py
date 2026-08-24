from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


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
