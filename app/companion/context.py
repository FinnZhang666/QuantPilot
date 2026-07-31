import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Tuple

from app.companion.schemas import CompanionContext
from app.trade_review.service import TradeReviewService


MAX_UNTRUSTED_TEXT = 1000


class CompanionContextBuilder:
    def __init__(self, repository, statistics_service: TradeReviewService):
        self.repository = repository
        self.statistics_service = statistics_service

    def build_trade_plan_context(self, plan_id: str) -> Tuple[CompanionContext, object, dict]:
        plan = self.repository.get_plan(plan_id)
        if plan is None:
            raise KeyError("Trade Plan不存在。")
        if plan.lifecycle_stage not in ("PLAN", "COMPANION", "REVIEW", "CANCELLED", "EXPIRED"):
            raise ValueError("当前Trade Plan阶段不允许生成AI Companion解释。")
        return self._build("TRADE_PLAN", plan, None, None)

    def build_user_position_context(self, position_id: int):
        position = self.repository.get_position(position_id)
        if position is None:
            raise KeyError("User Position不存在。")
        plan = self.repository.get_plan_by_id(position.trade_plan_id)
        if plan is None:
            raise ValueError("User Position关联的Trade Plan不存在。")
        return self._build("USER_POSITION", plan, position, None)

    def build_trade_review_context(self, review_id: int):
        review = self.repository.get_review(review_id)
        if review is None:
            raise KeyError("Trade Review不存在。")
        plan = self.repository.get_plan_by_id(review.trade_plan_id)
        if plan is None:
            raise ValueError("Trade Review关联的Trade Plan不存在。")
        position = self.repository.get_position(review.user_position_id) if review.user_position_id else None
        return self._build("TRADE_REVIEW", plan, position, review)

    def build_statistics_context(self):
        statistics = json.loads(json.dumps(self.statistics_service.statistics()))
        marker = self.repository.latest_review_updated_at()
        updated = _aware(marker) if marker else datetime(1970, 1, 1, tzinfo=timezone.utc)
        refs = {
            "trade_plan_id": None, "user_position_id": None,
            "trade_review_id": None, "user_id": None,
            "object_updated_at": updated.isoformat(), "statistics_scope": "GLOBAL",
        }
        return CompanionContext(
            context_type="STATISTICS", generated_at=updated, trade_plan=None,
            statistics=statistics, missing_fields=[], source_references=refs,
        ), updated, refs

    def _build(self, context_type, plan, position, review):
        signal = self.repository.get_signal(plan.signal_id)
        plan_data = {
            "trade_plan_id": plan.plan_id, "symbol": plan.symbol, "market": plan.market,
            "direction": plan.direction, "lifecycle_stage": plan.lifecycle_stage,
            "status": plan.plan_status, "strategy_id": plan.strategy_name,
            "strategy_version": plan.strategy_version, "signal_score": plan.score,
            "confidence": plan.confidence, "timeframe": plan.timeframe,
            "reference_price": _value(plan.reference_price),
            "buy_zone": _zone(plan.buy_zone_lower, plan.buy_zone_upper),
            "add_on_zone": _zone(plan.trend_add_on_zone_lower, plan.trend_add_on_zone_upper),
            "breakout_zone": _zone(plan.breakout_zone_lower, plan.breakout_zone_upper),
            "stop_loss": _value(plan.stop_loss_price),
            "targets": [_value(value) for value in (plan.target_prices_json or [])],
            "strategy_snapshot": sanitize_untrusted(plan.source_metadata_json or {}),
            "source_signal_id": plan.signal_id,
            "signal_created_at": _time(signal.created_at) if signal else None,
            "plan_created_at": _time(plan.created_at),
        }
        position_data = None if position is None else {
            "user_position_id": position.id, "trade_plan_id": plan.plan_id,
            "status": position.status, "direction": position.direction,
            "entry_price": _value(position.entry_price), "quantity": _value(position.quantity),
            "opened_at": _time(position.opened_at), "closed_at": _time(position.closed_at),
            "exit_price": _value(position.exit_price),
            "notes": sanitize_untrusted(position.notes), "source": position.source,
        }
        review_data = None if review is None else {
            "review_id": review.id, "review_type": review.review_type,
            "result": review.result, "entry_price": _value(review.entry_price),
            "exit_price": _value(review.exit_price), "mfe": _value(review.mfe),
            "mae": _value(review.mae), "holding_minutes": review.holding_minutes,
            "target_hit": review.target_hit, "stop_hit": review.stop_hit,
            "review_time": _time(review.review_time),
        }
        missing = []
        for name in ("reference_price", "buy_zone", "add_on_zone", "breakout_zone", "stop_loss"):
            if plan_data[name] is None or plan_data[name] == {"lower": None, "upper": None}:
                missing.append(name)
        if not plan_data["targets"]:
            missing.append("targets")
        updated = max(value for value in (
            _aware(plan.updated_at), _aware(position.updated_at) if position else None,
            _aware(review.updated_at) if review else None,
        ) if value is not None)
        refs = {
            "trade_plan_id": plan.id,
            "user_position_id": position.id if position else None,
            "trade_review_id": review.id if review else None,
            "user_id": position.user_id if position else None,
            "object_updated_at": updated.isoformat(),
        }
        context = CompanionContext(
            context_type=context_type, generated_at=updated,
            trade_plan=plan_data, user_position=position_data, review=review_data,
            statistics=json.loads(json.dumps(self.statistics_service.statistics())),
            missing_fields=missing, source_references=refs,
        )
        return context, updated, refs


def sanitize_untrusted(value):
    if isinstance(value, str):
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
        return cleaned[:MAX_UNTRUSTED_TEXT]
    if isinstance(value, dict):
        return {str(key)[:100]: sanitize_untrusted(item) for key, item in list(value.items())[:100]}
    if isinstance(value, list):
        return [sanitize_untrusted(item) for item in value[:100]]
    return value


def _value(value):
    if value is None:
        return None
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.00000001")))
    except (InvalidOperation, ValueError):
        return str(value)


def _zone(lower, upper):
    return {"lower": _value(lower), "upper": _value(upper)}


def _time(value):
    return _aware(value).isoformat() if value is not None else None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
