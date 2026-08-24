from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class DataStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    STALE = "STALE"
    PERMISSION_DENIED = "PERMISSION_DENIED"


DEFAULT_TTL_SECONDS = {
    "universe": 24 * 60 * 60,
    "fundamentals": 120 * 24 * 60 * 60,
    "daily_bars": 3 * 24 * 60 * 60,
    "intraday_bars": 15 * 60,
    "money_flow": 30 * 60,
    "market_context": 15 * 60,
    "sector_context": 60 * 60,
}


@dataclass(frozen=True)
class DataQuality:
    available: bool
    status: str
    freshness: str
    coverage: float
    source: str
    confidence: str
    timestamp: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def as_dict(self):
        return asdict(self)


def assess_quality(data_type: str, timestamp: Optional[datetime], coverage: float,
                   source: str, status: Optional[str] = None,
                   error_code: Optional[str] = None,
                   error_message: Optional[str] = None,
                   now: Optional[datetime] = None, ttl_seconds: Optional[int] = None):
    coverage = max(0.0, min(1.0, float(coverage or 0)))
    now = now or datetime.now(timezone.utc)
    if timestamp is not None and timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    ttl = timedelta(seconds=ttl_seconds or DEFAULT_TTL_SECONDS[data_type])
    stale = timestamp is not None and now - timestamp > ttl
    resolved = status or (DataStatus.AVAILABLE.value if coverage >= 1 else
                          DataStatus.PARTIAL.value if coverage > 0 else
                          DataStatus.UNAVAILABLE.value)
    if stale and resolved in (DataStatus.AVAILABLE.value, DataStatus.PARTIAL.value):
        resolved = DataStatus.STALE.value
    available = resolved in (DataStatus.AVAILABLE.value, DataStatus.PARTIAL.value)
    confidence = ("HIGH" if available and coverage >= .8 and not stale else
                  "MEDIUM" if available and coverage >= .5 and not stale else
                  "LOW" if coverage > 0 else "INSUFFICIENT")
    return DataQuality(available, resolved, "STALE" if stale else "FRESH" if timestamp else "UNKNOWN",
                       coverage, source, confidence, timestamp, error_code, error_message)
