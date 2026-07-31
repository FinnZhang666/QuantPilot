import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.trade_review.metrics import calculate_excursions, classify_result
from app.trade_review.repository import TradeReviewRepository

logger = logging.getLogger(__name__)


class TradeReviewRuntime:
    def __init__(self, db: Session, repository: Optional[TradeReviewRepository] = None):
        self.repository = repository or TradeReviewRepository(db)

    def generate_review(self, review_type: str, source_id: int, dry_run: bool = True):
        normalized = review_type.upper()
        if normalized == "SYSTEM":
            source = self.repository.get_plan(source_id)
            if source is None:
                raise KeyError("Trade Plan不存在。")
            values = self._system_values(source)
        elif normalized == "USER":
            source = self.repository.get_position(source_id)
            if source is None:
                raise KeyError("User Position不存在。")
            values = self._user_values(source)
        else:
            raise ValueError("Review Type必须是SYSTEM或USER。")
        existing = self.repository.get_by_key(values["review_key"])
        if not dry_run:
            row = self.repository.save(values, existing)
            self.repository.commit()
            return row, existing is None
        return values, existing is None

    def generate_reviews(
        self, dry_run: bool = True, limit: int = 100, symbol: Optional[str] = None,
        strategy: Optional[str] = None, start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, object]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit必须在1到1000之间。")
        if start_time and end_time and self._aware(start_time) > self._aware(end_time):
            raise ValueError("start_time不能晚于end_time。")
        sources = self.repository.ended_sources(limit, symbol, strategy, start_time, end_time)
        result = {
            "dry_run": dry_run, "scanned": len(sources), "created": 0,
            "skipped": 0, "updated": 0, "failed": 0, "errors": [],
        }
        for review_type, source in sources:
            try:
                _, created = self.generate_review(review_type, source.id, dry_run)
                result["created" if created else "updated"] += 1
            except Exception as exc:
                self.repository.rollback()
                logger.warning(
                    "Trade Review failed type=%s source_id=%s error=%s",
                    review_type, source.id, type(exc).__name__,
                )
                result["failed"] += 1
                result["errors"].append({
                    "review_type": review_type, "source_id": source.id,
                    "error": type(exc).__name__, "message": str(exc),
                })
        result["status"] = "SUCCESS" if not result["failed"] else "PARTIAL_SUCCESS"
        return result

    def _system_values(self, plan):
        if plan.lifecycle_stage not in ("REVIEW", "CANCELLED", "EXPIRED"):
            raise ValueError("未结束的Trade Plan不得生成最终Review。")
        if plan.reference_price is None:
            raise ValueError("Trade Plan缺少Entry Reference Price。")
        started = self._aware(plan.created_at)
        finished = self._aware(self.repository.terminal_time(plan))
        bars = self.repository.bars(plan.symbol, plan.timeframe, started, finished)
        if not bars:
            raise ValueError("复盘区间没有可用历史K线。")
        exit_price = bars[-1].close
        result = {
            "CANCELLED": "CANCELLED", "EXPIRED": "EXPIRED",
        }.get(plan.lifecycle_stage, classify_result(plan.reference_price, exit_price, plan.direction))
        return self._values(
            "SYSTEM:%s" % plan.id, plan, None, result, plan.reference_price,
            exit_price, started, finished, bars,
        )

    def _user_values(self, position):
        if position.status != "CLOSED" or position.closed_at is None or position.exit_price is None:
            raise ValueError("只有CLOSED User Position可以生成最终Review。")
        plan = self.repository.get_plan(position.trade_plan_id)
        if plan is None:
            raise ValueError("User Position关联的Trade Plan不存在。")
        started, finished = self._aware(position.opened_at), self._aware(position.closed_at)
        bars = self.repository.bars(position.symbol, plan.timeframe, started, finished)
        if not bars:
            raise ValueError("复盘区间没有可用历史K线。")
        result = classify_result(position.entry_price, position.exit_price, position.direction)
        return self._values(
            "USER:%s" % position.id, plan, position, result, position.entry_price,
            position.exit_price, started, finished, bars,
        )

    def _values(self, key, plan, position, result, entry, exit_price, started, finished, bars):
        targets = plan.target_prices_json or []
        target = targets[0] if targets else None
        metrics = calculate_excursions(
            entry, bars, plan.direction, target, plan.stop_loss_price,
        )
        return {
            "review_key": key, "trade_plan_id": plan.id,
            "user_position_id": position.id if position else None,
            "review_type": "USER" if position else "SYSTEM", "result": result,
            "entry_price": entry, "exit_price": exit_price,
            "mfe": metrics["mfe"], "mae": metrics["mae"],
            "holding_minutes": max(0, int((finished - started).total_seconds() // 60)),
            "target_hit": metrics["target_hit"], "stop_hit": metrics["stop_hit"],
            "review_time": finished,
        }

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
