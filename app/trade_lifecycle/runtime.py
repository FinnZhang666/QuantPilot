import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.trade_lifecycle.repository import TradePlanRepository
from app.trade_lifecycle.service import TradeLifecycleService
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TradePlanRuntime:
    """Convert confirmed strategy signals into lifecycle-managed Trade Plans."""

    def __init__(
        self, db: Session, repository: Optional[TradePlanRepository] = None,
        service: Optional[TradeLifecycleService] = None,
        now_provider=None,
        candidate_max_age_hours: Optional[int] = None,
    ):
        self.repository = repository or TradePlanRepository(db)
        self.service = service or TradeLifecycleService(db, repository=self.repository)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.candidate_max_age_hours = (
            candidate_max_age_hours
            if candidate_max_age_hours is not None
            else get_settings().candidate_pool_expiry_hours
        )

    def run(self, limit: int = 100) -> Dict[str, object]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit必须在1到1000之间。")
        cutoff = self.now_provider() - timedelta(hours=self.candidate_max_age_hours)
        signals = self.repository.pending_candidate_signals(
            limit, not_before=cutoff,
        )
        created = 0
        promoted = 0
        refreshed = 0
        errors: List[Dict[str, object]] = []
        plan_ids: List[str] = []
        for signal in signals:
            try:
                plan, was_created = self.service.create_from_signal(signal.id)
                created += int(was_created)
                refreshed += int(not was_created)
                if plan.lifecycle_stage == "DISCOVER":
                    plan = self.service.advance(
                        plan.plan_id, "PLAN",
                        "Strategy Engine已确认CANDIDATE_BUY，Trade Plan进入计划阶段。",
                        "TRADE_PLAN_RUNTIME",
                        {"signal_id": signal.id, "signal_type": signal.signal_type},
                    )
                    promoted += 1
                plan_ids.append(plan.plan_id)
            except Exception as exc:
                self.repository.rollback()
                logger.exception("Trade Plan generation failed for signal_id=%s", signal.id)
                errors.append({
                    "signal_id": signal.id, "symbol": signal.symbol,
                    "error": type(exc).__name__, "message": str(exc),
                })
        return {
            "status": "SUCCESS" if not errors else "PARTIAL_SUCCESS",
            "scanned": len(signals), "created": created, "promoted": promoted,
            "refreshed": refreshed, "errors_count": len(errors),
            "errors": errors, "plan_ids": plan_ids,
        }
