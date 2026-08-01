from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SystemPaperPosition, TradePlan, TradeReview
from app.paper_runtime.audit import PaperAudit


D = Decimal


class SystemPaperReviewService:
    """Creates immutable, fill-based SYSTEM reviews only after a paper position closes."""

    def __init__(self, db: Session):
        self.db = db
        self.audit = PaperAudit(db)

    def generate_pending(self, limit: int = 100):
        positions = list(self.db.scalars(select(SystemPaperPosition).where(
            SystemPaperPosition.status == "CLOSED",
            SystemPaperPosition.close_time.is_not(None),
            SystemPaperPosition.exit_price.is_not(None),
        ).order_by(SystemPaperPosition.close_time, SystemPaperPosition.id).limit(limit)))
        created = skipped = failed = 0
        errors = []
        for position in positions:
            key = self.review_key(position)
            if self.db.scalar(select(TradeReview.id).where(TradeReview.review_key == key)):
                skipped += 1
                continue
            try:
                self.generate(position)
                created += 1
            except Exception as exc:
                failed += 1
                errors.append({"position_id": position.id, "error": type(exc).__name__})
        self.db.commit()
        return {
            "status": "SUCCESS" if not failed else "PARTIAL_SUCCESS",
            "scanned": len(positions), "created": created,
            "skipped": skipped, "failed": failed, "errors": errors,
        }

    def generate(self, position: SystemPaperPosition) -> TradeReview:
        if position.status != "CLOSED" or position.close_time is None or position.exit_price is None:
            raise ValueError("Only a fully closed system paper position can be reviewed.")
        key = self.review_key(position)
        existing = self.db.scalar(select(TradeReview).where(TradeReview.review_key == key))
        if existing:
            return existing
        plan = self.db.get(TradePlan, position.trade_plan_id)
        if plan is None:
            raise ValueError("System paper position is missing its Trade Plan.")
        initial_quantity = D(str(position.initial_quantity or 0))
        notional = D(str(position.average_entry)) * initial_quantity
        realized_return = D(str(position.realized_pnl)) / notional if notional else D("0")
        result = "WIN" if realized_return > 0 else "LOSS" if realized_return < 0 else "BREAKEVEN"
        holding_minutes = max(
            0, int((self._aware(position.close_time) - self._aware(position.open_time)).total_seconds() // 60),
        )
        row = TradeReview(
            review_key=key, trade_plan_id=plan.id, user_position_id=None,
            system_paper_position_id=position.id, review_type="SYSTEM", result=result,
            entry_price=position.average_entry, exit_price=position.exit_price,
            mfe=position.mfe, mae=position.mae, holding_minutes=holding_minutes,
            target_hit=(position.exit_reason or "").startswith("TARGET_"),
            stop_hit=position.exit_reason in {"STOP_LOSS", "AMBIGUOUS_STOP_PRIORITY"},
            realized_return=realized_return, exit_reason=position.exit_reason,
            strategy_name=position.strategy_name,
            strategy_version=position.strategy_version,
            fill_model_version=position.fill_model_version,
            data_quality=position.data_quality,
            source_snapshot_json={
                "source": "SYSTEM_PAPER_POSITION",
                "position_id": position.id,
                "candidate_id": plan.signal_id,
                "trade_plan_id": plan.id,
                "direction": position.direction,
                "timeframe": position.timeframe,
                "entry": str(position.average_entry),
                "exit": str(position.exit_price),
                "initial_quantity": str(initial_quantity),
                "realized_pnl": str(position.realized_pnl),
                "realized_return": str(realized_return),
                "mfe": str(position.mfe),
                "mae": str(position.mae),
                "exit_reason": position.exit_reason,
                "fill_model_version": position.fill_model_version,
                "exit_rule_version": position.exit_rule_version,
                "data_quality": position.data_quality,
            },
            review_time=position.close_time,
        )
        self.db.add(row)
        self.db.flush()
        plan.review_status = "COMPLETED"
        self.audit.record(
            "REVIEW_GENERATED", candidate_id=plan.signal_id, trade_plan_id=plan.id,
            position_id=position.id, review_id=row.id,
            details={"review_key": key, "result": result},
        )
        return row

    @staticmethod
    def review_key(position: SystemPaperPosition) -> str:
        return "SYSTEM_PAPER:%s:%s" % (position.id, position.fill_model_version)

    @staticmethod
    def _aware(value):
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
