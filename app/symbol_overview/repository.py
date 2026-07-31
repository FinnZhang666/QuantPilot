from sqlalchemy import desc, or_, select

from app.database.models import CompanionAnalysis, TradeReview


class SymbolOverviewRepository:
    """Read-only relationship lookup; no flush, commit, or business calculation."""

    def __init__(self, db):
        self.db = db

    def latest_review(self, plan_id=None, holding=None):
        conditions = []
        if plan_id:
            conditions.append(TradeReview.trade_plan_id == plan_id)
        if holding and holding.user_position_id:
            conditions.append(TradeReview.user_position_id == holding.user_position_id)
        if not conditions:
            return None
        return self.db.scalar(select(TradeReview).where(or_(*conditions)).order_by(
            desc(TradeReview.review_time), desc(TradeReview.id),
        ).limit(1))

    def analyses(self, plan_id=None, holding=None, review_id=None, limit=20):
        conditions = []
        if plan_id:
            conditions.append(CompanionAnalysis.trade_plan_id == plan_id)
        if holding and holding.user_position_id:
            conditions.append(CompanionAnalysis.user_position_id == holding.user_position_id)
        if review_id:
            conditions.append(CompanionAnalysis.trade_review_id == review_id)
        if not conditions:
            return []
        return list(self.db.scalars(select(CompanionAnalysis).where(
            or_(*conditions), CompanionAnalysis.status == "COMPLETED",
        ).order_by(desc(CompanionAnalysis.created_at), desc(CompanionAnalysis.id)).limit(limit)))
