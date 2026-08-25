from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from app.core.errors import AppError


class DataFreshness(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"


@dataclass(frozen=True)
class DataEnvelope:
    value: Any
    source: str
    market_timestamp: Optional[datetime]
    received_timestamp: datetime
    age_seconds: float
    freshness: DataFreshness
    completeness: float
    error: Optional[AppError] = None

    def safe_metadata(self):
        return {"source": self.source,
                "market_timestamp": self.market_timestamp,
                "received_timestamp": self.received_timestamp,
                "age_seconds": round(self.age_seconds, 3),
                "freshness": self.freshness.value,
                "completeness": self.completeness,
                "error": self.error.safe_dict() if self.error else None}
