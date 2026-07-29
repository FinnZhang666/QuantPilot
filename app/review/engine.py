from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from app.review.metrics import calculate_metrics, directional_return


class OpportunityReviewEngine:
    def evaluate(
        self, opportunity, bars: List[Dict[str, object]],
        windows: Dict[str, object], config_version: str,
        atr: Optional[Decimal] = None,
    ) -> Dict[str, object]:
        entry = Decimal(str(opportunity.entry_reference_price))
        target = _decimal(opportunity.target_reference_price)
        stop = _decimal(opportunity.stop_reference_price)
        metrics = calculate_metrics(entry, bars, opportunity.direction, target, stop)
        holding_seconds = max(
            0, int((_aware(bars[-1]["timestamp"]) - _aware(opportunity.bar_time)).total_seconds()),
        )
        metrics["holding_seconds"] = holding_seconds
        metrics["holding_minutes"] = holding_seconds // 60
        metrics["holding_days"] = Decimal(holding_seconds) / Decimal("86400")
        window_returns = {}
        for name, duration in windows.items():
            deadline = _aware(opportunity.bar_time) + duration
            eligible = [item for item in bars if _aware(item["timestamp"]) <= deadline]
            window_returns[name] = (
                str(directional_return(entry, Decimal(str(eligible[-1]["close"])), opportunity.direction))
                if eligible else None
            )
        risk = abs(entry - stop) if stop is not None else None
        reward = abs(target - entry) if target is not None else None
        risk_reward = reward / risk if risk and risk > 0 and reward is not None else None
        atr_multiple = (
            abs(metrics["exit_price"] - entry) / atr if atr is not None and atr > 0 else None
        )
        return {
            "metrics": metrics,
            "statistics": {
                "highest_price": str(metrics["highest_price"]),
                "lowest_price": str(metrics["lowest_price"]),
                "holding_seconds": metrics["holding_seconds"],
                "atr": str(atr) if atr is not None else None,
                "atr_multiple": str(atr_multiple) if atr_multiple is not None else None,
                "risk_reward": str(risk_reward) if risk_reward is not None else None,
                "window_returns": window_returns,
                "review_completed_at": datetime.utcnow().isoformat() + "Z",
                "config_version": config_version,
            },
        }


def _decimal(value):
    return Decimal(str(value)) if value is not None else None


def _aware(value):
    from datetime import timezone
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
