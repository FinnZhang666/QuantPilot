from copy import deepcopy
from decimal import Decimal
from typing import Optional

from app.database.models import CandidateSignal
from app.trade_lifecycle.domain import TradeDirection, TradePlanDraft, normalize_direction


class TradePlanAdapter:
    """Deterministically maps persisted Strategy output without recalculation."""

    SUPPORTED_SIGNAL_TYPES = {"CANDIDATE_BUY"}

    def from_candidate_signal(
        self, signal: CandidateSignal, direction: Optional[str] = None,
        reference_price: Optional[Decimal] = None,
    ) -> TradePlanDraft:
        if signal.signal_type not in self.SUPPORTED_SIGNAL_TYPES:
            raise ValueError("该策略输出不会创建Trade Plan：%s" % signal.signal_type)
        mapped_direction = (
            normalize_direction(direction) if direction is not None else TradeDirection.LONG
        )
        snapshot = {
            "source_type": "CANDIDATE_SIGNAL",
            "signal": {
                "id": signal.id,
                "symbol": signal.symbol,
                "market": signal.market,
                "timeframe": signal.timeframe,
                "bar_timestamp": _iso(signal.bar_timestamp),
                "strategy_name": signal.strategy_name,
                "strategy_version": signal.strategy_version,
                "parameters_hash": signal.parameters_hash,
                "signal_type": signal.signal_type,
                "score": signal.score,
                "confidence": signal.confidence,
                "status": signal.status,
                "summary_zh": signal.summary_zh,
                "reasons": deepcopy(signal.reasons_json or []),
                "risks": deepcopy(signal.risks_json or []),
                "feature_refs": deepcopy(signal.feature_refs_json or {}),
                "components": deepcopy(signal.components_json or {}),
            },
            "levels": {
                "availability": "UNAVAILABLE",
                "reason": "现有Strategy Engine未提供结构化价格区间，未进行推导。",
            },
        }
        return TradePlanDraft(
            symbol=signal.symbol,
            market=signal.market,
            strategy_name=signal.strategy_name,
            strategy_version=signal.strategy_version,
            signal_id=signal.id,
            direction=mapped_direction,
            timeframe=signal.timeframe,
            reference_price=reference_price,
            confidence=signal.confidence,
            score=signal.score,
            source_metadata=snapshot,
        )


def _iso(value):
    return value.isoformat() if value is not None else None
