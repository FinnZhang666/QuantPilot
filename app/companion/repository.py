from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func, select

from app.database.models import (
    CandidateSignal, CompanionAnalysis, TradePlan, TradeReview, UserPosition,
)


class CompanionRepository:
    def __init__(self, db):
        self.db = db

    def get_plan(self, plan_id: str) -> Optional[TradePlan]:
        return self.db.scalar(select(TradePlan).where(TradePlan.plan_id == plan_id))

    def get_plan_by_id(self, plan_id: int) -> Optional[TradePlan]:
        return self.db.get(TradePlan, plan_id)

    def get_position(self, position_id: int) -> Optional[UserPosition]:
        return self.db.get(UserPosition, position_id)

    def get_review(self, review_id: int) -> Optional[TradeReview]:
        return self.db.get(TradeReview, review_id)

    def get_signal(self, signal_id: Optional[int]):
        return self.db.get(CandidateSignal, signal_id) if signal_id else None

    def get_analysis(self, analysis_id: int):
        return self.db.get(CompanionAnalysis, analysis_id)

    def find_key(self, analysis_key: str):
        return self.db.scalar(select(CompanionAnalysis).where(
            CompanionAnalysis.analysis_key == analysis_key,
        ))

    def find_cached(self, request_fingerprint: str):
        return self.db.scalar(select(CompanionAnalysis).where(
            CompanionAnalysis.request_fingerprint == request_fingerprint,
            CompanionAnalysis.status == "COMPLETED",
            CompanionAnalysis.cache_key.is_not(None),
        ).order_by(desc(CompanionAnalysis.id)).limit(1))

    def find_slot(self, cache_key: str):
        return self.db.scalar(select(CompanionAnalysis).where(
            CompanionAnalysis.cache_key == cache_key,
        ))

    def latest_review_updated_at(self):
        from app.database.models import TradeReview
        return self.db.scalar(select(func.max(TradeReview.updated_at)))

    def save(self, values: dict, existing=None):
        row = existing or CompanionAnalysis()
        for key, value in values.items():
            setattr(row, key, value)
        self.db.add(row)
        self.db.flush()
        return row

    def list(self, context_type=None, trade_plan_id=None, user_position_id=None,
             trade_review_id=None, status=None, language=None, provider=None,
             start_time=None, end_time=None, limit=100, offset=0):
        query = self._filtered(
            context_type, trade_plan_id, user_position_id, trade_review_id,
            status, language, provider, start_time, end_time,
        )
        return list(self.db.scalars(query.order_by(
            desc(CompanionAnalysis.created_at), desc(CompanionAnalysis.id),
        ).offset(offset).limit(limit)))

    def count(self, context_type=None, trade_plan_id=None, user_position_id=None,
              trade_review_id=None, status=None, language=None, provider=None,
              start_time=None, end_time=None):
        query = self._filtered(
            context_type, trade_plan_id, user_position_id, trade_review_id,
            status, language, provider, start_time, end_time,
        ).subquery()
        return int(self.db.scalar(select(func.count()).select_from(query)) or 0)

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    @staticmethod
    def _filtered(context_type=None, trade_plan_id=None, user_position_id=None,
                  trade_review_id=None, status=None, language=None, provider=None,
                  start_time=None, end_time=None):
        query = select(CompanionAnalysis)
        for field, value in (
            (CompanionAnalysis.context_type, context_type),
            (CompanionAnalysis.trade_plan_id, trade_plan_id),
            (CompanionAnalysis.user_position_id, user_position_id),
            (CompanionAnalysis.trade_review_id, trade_review_id),
            (CompanionAnalysis.status, status), (CompanionAnalysis.language, language),
            (CompanionAnalysis.provider, provider),
        ):
            if value is not None:
                query = query.where(field == (value.upper() if field in (
                    CompanionAnalysis.context_type, CompanionAnalysis.status,
                ) else value))
        if start_time:
            query = query.where(CompanionAnalysis.created_at >= start_time)
        if end_time:
            query = query.where(CompanionAnalysis.created_at <= end_time)
        return query
