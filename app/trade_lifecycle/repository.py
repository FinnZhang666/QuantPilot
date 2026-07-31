from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.database.models import CandidateSignal, TradePlan, TradePlanTransition


class TradePlanRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_signal(self, signal_id: int) -> Optional[CandidateSignal]:
        return self.db.get(CandidateSignal, signal_id)

    def pending_candidate_signals(self, limit: int = 100) -> List[CandidateSignal]:
        query = select(CandidateSignal).outerjoin(
            TradePlan,
            and_(
                TradePlan.signal_id == CandidateSignal.id,
                TradePlan.direction == "LONG",
            ),
        ).where(
            CandidateSignal.signal_type == "CANDIDATE_BUY",
            CandidateSignal.status == "VALID",
            or_(TradePlan.id.is_(None), TradePlan.lifecycle_stage == "DISCOVER"),
        ).order_by(CandidateSignal.bar_timestamp, CandidateSignal.id).limit(limit)
        return list(self.db.scalars(query))

    def find_by_signal(self, signal_id: int, direction: str) -> Optional[TradePlan]:
        return self.db.scalar(select(TradePlan).where(
            TradePlan.signal_id == signal_id, TradePlan.direction == direction,
        ))

    def exists(self, signal_id: int, direction: str = "LONG") -> bool:
        return self.find_by_signal(signal_id, direction) is not None

    def add(self, row: TradePlan) -> TradePlan:
        self.db.add(row)
        self.db.flush()
        return row

    def update_from_draft(self, row: TradePlan, draft) -> TradePlan:
        row.score = draft.score
        row.confidence = draft.confidence
        row.source_metadata_json = dict(draft.source_metadata)
        if draft.reference_price is not None:
            row.reference_price = draft.reference_price
        self.db.add(row)
        return row

    def get(self, plan_id: str) -> Optional[TradePlan]:
        return self.db.scalar(select(TradePlan).where(TradePlan.plan_id == plan_id))

    def list(
        self, symbol: Optional[str] = None, lifecycle_stage: Optional[str] = None,
        status: Optional[str] = None, strategy: Optional[str] = None,
        market: Optional[str] = None, start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None, limit: int = 100, offset: int = 0,
    ) -> List[TradePlan]:
        query = self._filtered(
            symbol, lifecycle_stage, status, strategy, market, start_time, end_time,
        )
        return list(self.db.scalars(query.order_by(
            desc(TradePlan.created_at), desc(TradePlan.id),
        ).offset(offset).limit(limit)))

    def count(
        self, symbol: Optional[str] = None, lifecycle_stage: Optional[str] = None,
        status: Optional[str] = None, strategy: Optional[str] = None,
        market: Optional[str] = None, start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        filtered = self._filtered(
            symbol, lifecycle_stage, status, strategy, market, start_time, end_time,
        ).subquery()
        return int(self.db.scalar(select(func.count()).select_from(filtered)) or 0)

    def history(self, trade_plan_id: int) -> List[TradePlanTransition]:
        return list(self.db.scalars(select(TradePlanTransition).where(
            TradePlanTransition.trade_plan_id == trade_plan_id,
        ).order_by(TradePlanTransition.transitioned_at, TradePlanTransition.id)))

    def add_transition(self, row: TradePlanTransition) -> None:
        self.db.add(row)

    def save(self, row: TradePlan) -> None:
        self.db.add(row)

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    @staticmethod
    def _filtered(
        symbol=None, lifecycle_stage=None, status=None, strategy=None,
        market=None, start_time=None, end_time=None,
    ):
        query = select(TradePlan)
        if symbol:
            query = query.where(TradePlan.symbol == symbol.upper().replace("US.", ""))
        if lifecycle_stage:
            query = query.where(TradePlan.lifecycle_stage == lifecycle_stage)
        if status:
            query = query.where(TradePlan.plan_status == status.upper())
        if strategy:
            query = query.where(TradePlan.strategy_name == strategy)
        if market:
            query = query.where(TradePlan.market == market.upper())
        if start_time:
            query = query.where(TradePlan.created_at >= start_time)
        if end_time:
            query = query.where(TradePlan.created_at <= end_time)
        return query
