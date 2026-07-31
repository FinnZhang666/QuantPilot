import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.database.models import TradePlan, TradePlanTransition
from app.trade_lifecycle.adapter import TradePlanAdapter
from app.trade_lifecycle.domain import (
    ALLOWED_TRANSITIONS, LifecycleStage, TradePlanDraft, TradePlanStatus,
    normalize_stage,
)
from app.trade_lifecycle.repository import TradePlanRepository


class TradeLifecycleService:
    def __init__(
        self, db: Session, adapter: Optional[TradePlanAdapter] = None,
        repository: Optional[TradePlanRepository] = None,
    ):
        self.adapter = adapter or TradePlanAdapter()
        self.repository = repository or TradePlanRepository(db)

    def create_from_signal(
        self, signal_id: int, direction: Optional[str] = None,
    ) -> Tuple[TradePlan, bool]:
        signal = self.repository.get_signal(signal_id)
        if signal is None:
            raise KeyError("Candidate Signal不存在。")
        draft = self.adapter.from_candidate_signal(signal, direction=direction)
        existing = self.repository.find_by_signal(draft.signal_id, draft.direction.value)
        if existing is not None:
            self.repository.update_from_draft(existing, draft)
            self.repository.commit()
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
        self.repository.add(row)
        self._record_transition(
            row, None, LifecycleStage.DISCOVER, "Trade Plan由策略输出适配创建。",
            "STRATEGY_ADAPTER", {"signal_id": draft.signal_id},
        )
        self.repository.commit()
        return row

    def get(self, plan_id: str) -> Optional[TradePlan]:
        return self.repository.get(plan_id)

    def list(
        self, symbol: Optional[str] = None, lifecycle_stage: Optional[str] = None,
        status: Optional[str] = None, strategy: Optional[str] = None,
        market: Optional[str] = None, start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None, limit: int = 100, offset: int = 0,
    ) -> List[TradePlan]:
        stage = normalize_stage(lifecycle_stage).value if lifecycle_stage else None
        return self.repository.list(
            symbol, stage, status, strategy, market, start_time, end_time, limit, offset,
        )

    def count(
        self, symbol: Optional[str] = None, lifecycle_stage: Optional[str] = None,
        status: Optional[str] = None, strategy: Optional[str] = None,
        market: Optional[str] = None, start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        stage = normalize_stage(lifecycle_stage).value if lifecycle_stage else None
        return self.repository.count(
            symbol, stage, status, strategy, market, start_time, end_time,
        )

    def history(self, plan_id: str) -> List[TradePlanTransition]:
        row = self._required(plan_id)
        return self.repository.history(row.id)

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
        self.repository.save(row)
        self.repository.commit()
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
        self.repository.add_transition(TradePlanTransition(
            trade_plan_id=row.id,
            previous_stage=previous.value if previous else None,
            new_stage=target.value, transitioned_at=datetime.now(timezone.utc),
            reason=reason.strip(), source=source.strip(), metadata_json=metadata,
        ))
