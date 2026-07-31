from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from app.database.models import (
    MarketBar, TradePlan, TradePlanTransition, TradeReview, UserPosition,
)


class TradeReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def ended_sources(
        self, limit: int, symbol: Optional[str] = None, strategy: Optional[str] = None,
        start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
    ) -> List[Tuple[str, object]]:
        plan_query = select(TradePlan).where(
            TradePlan.lifecycle_stage.in_(["REVIEW", "CANCELLED", "EXPIRED"]),
        )
        position_query = select(UserPosition).join(
            TradePlan, TradePlan.id == UserPosition.trade_plan_id,
        ).where(UserPosition.status == "CLOSED")
        normalized = symbol.upper().replace("US.", "") if symbol else None
        if normalized:
            plan_query = plan_query.where(TradePlan.symbol == normalized)
            position_query = position_query.where(UserPosition.symbol == normalized)
        if strategy:
            plan_query = plan_query.where(TradePlan.strategy_name == strategy)
            position_query = position_query.where(TradePlan.strategy_name == strategy)
        if start_time or end_time:
            plan_query = plan_query.join(TradePlanTransition, and_(
                TradePlanTransition.trade_plan_id == TradePlan.id,
                TradePlanTransition.new_stage == TradePlan.lifecycle_stage,
            ))
        if start_time:
            plan_query = plan_query.where(TradePlanTransition.transitioned_at >= start_time)
            position_query = position_query.where(UserPosition.closed_at >= start_time)
        if end_time:
            plan_query = plan_query.where(TradePlanTransition.transitioned_at <= end_time)
            position_query = position_query.where(UserPosition.closed_at <= end_time)
        plans = list(self.db.scalars(plan_query.order_by(TradePlan.created_at, TradePlan.id).limit(limit)))
        remaining = max(0, limit - len(plans))
        positions = list(self.db.scalars(position_query.order_by(
            UserPosition.closed_at, UserPosition.id,
        ).limit(remaining))) if remaining else []
        return [("SYSTEM", row) for row in plans] + [("USER", row) for row in positions]

    def get_plan(self, plan_id: int) -> Optional[TradePlan]:
        return self.db.get(TradePlan, plan_id)

    def get_position(self, position_id: int) -> Optional[UserPosition]:
        return self.db.get(UserPosition, position_id)

    def terminal_time(self, plan: TradePlan) -> datetime:
        value = self.db.scalar(select(TradePlanTransition.transitioned_at).where(
            TradePlanTransition.trade_plan_id == plan.id,
            TradePlanTransition.new_stage == plan.lifecycle_stage,
        ).order_by(desc(TradePlanTransition.transitioned_at), desc(TradePlanTransition.id)).limit(1))
        return value or plan.updated_at

    def bars(self, symbol: str, interval: str, start_time: datetime, end_time: datetime):
        full_symbol = symbol if symbol.startswith("US.") else "US." + symbol
        return list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol == full_symbol, MarketBar.interval == interval,
            MarketBar.timestamp_utc >= start_time, MarketBar.timestamp_utc <= end_time,
            MarketBar.adjustment_type == "FORWARD", MarketBar.data_source == "MOOMOO",
        ).order_by(MarketBar.timestamp_utc)))

    def get_by_key(self, review_key: str) -> Optional[TradeReview]:
        return self.db.scalar(select(TradeReview).where(TradeReview.review_key == review_key))

    def save(self, values: dict, existing: Optional[TradeReview] = None) -> TradeReview:
        row = existing or TradeReview()
        for key, value in values.items():
            setattr(row, key, value)
        self.db.add(row)
        self.db.flush()
        return row

    def get(self, review_id: int) -> Optional[TradeReview]:
        return self.db.get(TradeReview, review_id)

    def list(
        self, review_type=None, result=None, symbol=None, strategy=None,
        start_time=None, end_time=None, limit=100, offset=0,
    ) -> List[TradeReview]:
        query = self._filtered(review_type, result, symbol, strategy, start_time, end_time)
        return list(self.db.scalars(query.order_by(
            desc(TradeReview.review_time), desc(TradeReview.id),
        ).offset(offset).limit(limit)))

    def count(self, review_type=None, result=None, symbol=None, strategy=None, start_time=None, end_time=None):
        query = self._filtered(review_type, result, symbol, strategy, start_time, end_time).subquery()
        return int(self.db.scalar(select(func.count()).select_from(query)) or 0)

    def statistics(self):
        rows = self.db.execute(select(
            TradeReview.review_type, TradeReview.result, func.count(TradeReview.id),
        ).group_by(TradeReview.review_type, TradeReview.result)).all()
        result = {
            "system": {"total_reviews": 0, "wins": 0, "losses": 0, "breakeven": 0},
            "user": {"closed_positions": 0, "wins": 0, "losses": 0, "breakeven": 0},
        }
        for review_type, outcome, count in rows:
            group = result["system" if review_type == "SYSTEM" else "user"]
            group["total_reviews" if review_type == "SYSTEM" else "closed_positions"] += count
            key = {"WIN": "wins", "LOSS": "losses", "BREAKEVEN": "breakeven"}.get(outcome)
            if key:
                group[key] += count
        return result

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    @staticmethod
    def _filtered(review_type=None, result=None, symbol=None, strategy=None, start_time=None, end_time=None):
        query = select(TradeReview).join(TradePlan, TradePlan.id == TradeReview.trade_plan_id)
        if review_type:
            query = query.where(TradeReview.review_type == review_type.upper())
        if result:
            query = query.where(TradeReview.result == result.upper())
        if symbol:
            query = query.where(TradePlan.symbol == symbol.upper().replace("US.", ""))
        if strategy:
            query = query.where(TradePlan.strategy_name == strategy)
        if start_time:
            query = query.where(TradeReview.review_time >= start_time)
        if end_time:
            query = query.where(TradeReview.review_time <= end_time)
        return query
