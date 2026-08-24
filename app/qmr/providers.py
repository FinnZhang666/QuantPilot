from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.database.models import FundamentalSnapshot


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


class DatabaseFundamentalsProvider:
    def __init__(self, db):
        self.db = db

    def latest(self, symbol: str, evaluation_time: datetime) -> Optional[FundamentalSnapshot]:
        return self.db.scalar(select(FundamentalSnapshot).where(
            FundamentalSnapshot.symbol == symbol,
            FundamentalSnapshot.available_at <= evaluation_time,
        ).order_by(FundamentalSnapshot.available_at.desc()).limit(1))
