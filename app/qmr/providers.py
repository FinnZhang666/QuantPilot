from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.database.models import FundamentalSnapshot
from app.data.quality import assess_quality


class PointInTimeFundamentals:
    """Vendor-neutral view over the persisted point-in-time snapshot."""
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.symbol = snapshot.symbol
        self.as_of_date = snapshot.period_end.date()
        self.reported_at = snapshot.available_at
        self.period_end = snapshot.period_end
        self.available_at = snapshot.available_at
        self.source = snapshot.source
        payload = snapshot.source_payload_json or {}
        self.currency = payload.get("currency")
        fields = ("net_income_ttm", "eps_ttm", "operating_margin", "roe", "roic",
                  "revenue_yoy", "eps_yoy", "operating_cash_flow", "free_cash_flow",
                  "cash", "debt", "debt_to_equity")
        coverage = sum(getattr(snapshot, name) is not None for name in fields) / len(fields)
        quality = assess_quality("fundamentals", snapshot.available_at, coverage, snapshot.source)
        self.data_available = quality.available
        self.freshness = quality.freshness
        self.quality = quality.confidence

    def __getattr__(self, name):
        return getattr(self._snapshot, name)


@dataclass(frozen=True)
class EventAssessment:
    event_risk: str = "UNKNOWN"
    fundamental_risk: str = "UNKNOWN"
    confidence: str = "LOW"
    source: str = "NO_NEWS_PROVIDER"


class NewsProvider:
    def assess(self, symbol: str, evaluation_time: datetime) -> EventAssessment:
        raise NotImplementedError


class NoNewsProvider(NewsProvider):
    def assess(self, symbol: str, evaluation_time: datetime) -> EventAssessment:
        return EventAssessment()


class FundamentalsProvider:
    def get_latest(self, symbol: str, evaluation_time: Optional[datetime] = None):
        raise NotImplementedError

    def get_as_of(self, symbol: str, timestamp: datetime):
        raise NotImplementedError


class DatabaseFundamentalsProvider(FundamentalsProvider):
    def __init__(self, db):
        self.db = db

    def get_as_of(self, symbol: str, timestamp: datetime) -> Optional[FundamentalSnapshot]:
        row = self.db.scalar(select(FundamentalSnapshot).where(
            FundamentalSnapshot.symbol == symbol,
            FundamentalSnapshot.available_at <= timestamp,
        ).order_by(FundamentalSnapshot.available_at.desc()).limit(1))
        return PointInTimeFundamentals(row) if row else None

    def get_latest(self, symbol: str, evaluation_time: Optional[datetime] = None):
        return self.get_as_of(symbol, evaluation_time or datetime.max.replace(tzinfo=timezone.utc))

    def latest(self, symbol: str, evaluation_time: datetime):
        """Compatibility alias; point-in-time callers should prefer get_as_of."""
        return self.get_as_of(symbol, evaluation_time)
