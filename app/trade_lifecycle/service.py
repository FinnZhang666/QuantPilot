import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models import CandidateSignal, TradePlan, TradePlanTransition
from app.trade_lifecycle.adapter import TradePlanAdapter
from app.trade_lifecycle.domain import (
    ALLOWED_TRANSITIONS, LifecycleStage, TradePlanDraft, TradePlanStatus,
    normalize_stage,
)


class TradeLifecycleService:
    def __init__(self, db: Session, adapter: Optional[TradePlanAdapter] = None):
        self.db = db
        self.adapter = adapter or TradePlanAdapter()

    def create_from_signal(
        self, signal_id: int, direction: Optional[str] = None,
    ) -> Tuple[TradePlan, bool]:
        signal = self.db.get(CandidateSignal, signal_id)
        if signal is None:
            raise KeyError("Candidate Signal不存在。")
        draft = self.adapter.from_candidate_signal(signal, direction=direction)
        existing = self.db.scalar(select(TradePlan).where(
            TradePlan.signal_id == draft.signal_id,
            TradePlan.direction == draft.direction.value,
        ))
        if existing is not None:
            return existing, False
        return self.create(draft), True

    def create(self, draft: TradePlanDraft) -> TradePlan:
        row = TradePlan(
            plan_id=str(uuid.uuid4()), symbol=draft.symbol, market=draft.market,
            strategy_name=draft.strategy_name, strategy_version=draft.strategy_version,
            signal_id=draft.signal_id, lifecycle_stage=LifecycleStage.DISCOVER.value,
            direction=draft.direction.value, timeframe=draft.timeframe,
            reference_price=draft.reference_price,
            buy_zone_lower=draft.buy_zone_lower, buy_zone_upper=draft.buy_zone_upper,
            trend_add_on_zone_lower=draft.trend_add_on_zone_lower,
            trend_add_on_zone_upper=draft.trend_add_on_zone_upper,
            breakout_zone_lower=draft.breakout_zone_lower,
            breakout_zone_upper=draft.breakout_zone_upper,
            stop_loss_price=draft.stop_loss_price,
            target_prices_json=list(draft.target_prices),
            invalidation_condition=draft.invalidation_condition,
            confidence=draft.confidence, score=draft.score,
            plan_status=TradePlanStatus.ACTIVE.value,
            source_metadata_json=dict(draft.source_metadata),
            user_participation_status="NOT_DECLARED", review_status="NOT_STARTED",
        )
        self.db.add(row)
        self.db.flush()
        self._record_transition(
            row, None, LifecycleStage.DISCOVER, "Trade Plan由策略输出适配创建。",
            "STRATEGY_ADAPTER", {"signal_id": draft.signal_id},
        )
        self.db.commit()
        return row

    def get(self, plan_id: str) -> Optional[TradePlan]:
        return self.db.scalar(select(TradePlan).where(TradePlan.plan_id == plan_id))

    def list(
        self, symbol: Optional[str] = None, lifecycle_stage: Optional[str] = None,
        status: Optional[str] = None, strategy: Optional[str] = None,
        market: Optional[str] = None, start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None, limit: int = 100, offset: int = 0,
    ) -> List[TradePlan]:
        query = select(TradePlan)
        if symbol:
            query = query.where(TradePlan.symbol == symbol.upper().replace("US.", ""))
        if lifecycle_stage:
            query = query.where(TradePlan.lifecycle_stage == normalize_stage(lifecycle_stage).value)
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
        return list(self.db.scalars(query.order_by(
            desc(TradePlan.created_at), desc(TradePlan.id),
        ).offset(offset).limit(limit)))

    def history(self, plan_id: str) -> List[TradePlanTransition]:
        row = self._required(plan_id)
        return list(self.db.scalars(select(TradePlanTransition).where(
            TradePlanTransition.trade_plan_id == row.id,
        ).order_by(TradePlanTransition.transitioned_at, TradePlanTransition.id)))

    def advance(
        self, plan_id: str, new_stage, reason: str, source: str,
        metadata: Optional[Dict[str, object]] = None,
    ) -> TradePlan:
        if not reason.strip() or not source.strip():
            raise ValueError("生命周期转换必须记录reason和source。")
        row = self._required(plan_id)
        previous = normalize_stage(row.lifecycle_stage)
        target = normalize_stage(new_stage)
        if target not in ALLOWED_TRANSITIONS[previous]:
            raise ValueError("不允许的生命周期转换：%s → %s" % (previous.value, target.value))
        row.lifecycle_stage = target.value
        if target == LifecycleStage.CANCELLED:
            row.plan_status = TradePlanStatus.CANCELLED.value
        elif target == LifecycleStage.EXPIRED:
            row.plan_status = TradePlanStatus.EXPIRED.value
        if target == LifecycleStage.REVIEW:
            row.review_status = "PENDING"
        self._record_transition(row, previous, target, reason, source, metadata or {})
        self.db.commit()
        return row

    def cancel(self, plan_id: str, reason: str, source: str = "INTERNAL") -> TradePlan:
        return self.advance(plan_id, LifecycleStage.CANCELLED, reason, source)

    def expire(self, plan_id: str, reason: str, source: str = "SYSTEM") -> TradePlan:
        return self.advance(plan_id, LifecycleStage.EXPIRED, reason, source)

    def _required(self, plan_id: str) -> TradePlan:
        row = self.get(plan_id)
        if row is None:
            raise KeyError("Trade Plan不存在。")
        return row

    def _record_transition(
        self, row: TradePlan, previous: Optional[LifecycleStage], target: LifecycleStage,
        reason: str, source: str, metadata: Dict[str, object],
    ) -> None:
        self.db.add(TradePlanTransition(
            trade_plan_id=row.id,
            previous_stage=previous.value if previous else None,
            new_stage=target.value, transitioned_at=datetime.now(timezone.utc),
            reason=reason.strip(), source=source.strip(), metadata_json=metadata,
        ))
