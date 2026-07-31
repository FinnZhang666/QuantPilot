from datetime import timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.trade_review.repository import TradeReviewRepository


class TradeReviewService:
    def __init__(self, db: Session, repository: Optional[TradeReviewRepository] = None):
        self.repository = repository or TradeReviewRepository(db)

    def get(self, review_id: int):
        return self.repository.get(review_id)

    def list(self, review_type=None, result=None, symbol=None, strategy=None,
             start_time=None, end_time=None, limit=100, offset=0):
        self._validate(review_type, result)
        return self.repository.list(
            review_type, result, symbol, strategy, start_time, end_time, limit, offset,
        )

    def count(self, review_type=None, result=None, symbol=None, strategy=None,
              start_time=None, end_time=None):
        self._validate(review_type, result)
        return self.repository.count(review_type, result, symbol, strategy, start_time, end_time)

    def statistics(self):
        return self.repository.statistics()

    def source_plan(self, review):
        return self.repository.get_plan(review.trade_plan_id)

    @staticmethod
    def _validate(review_type, result):
        if review_type and review_type.upper() not in ("SYSTEM", "USER"):
            raise ValueError("Review Type无效。")
        if result and result.upper() not in (
            "WIN", "LOSS", "BREAKEVEN", "OPEN", "CANCELLED", "EXPIRED",
        ):
            raise ValueError("Review Result无效。")

    @staticmethod
    def aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
