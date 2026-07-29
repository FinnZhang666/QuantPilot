from typing import Dict, List, Tuple

from app.candidate_pool.models import FilterResult


def clamp(value):
    return max(0, min(100, int(round(value))))


class CandidateRanker:
    def __init__(self, min_score: int, both_gap: int):
        self.min_score = min_score
        self.both_gap = both_gap

    def rank_one(self, filters: List[FilterResult], regime) -> Dict[str, object]:
        long_score = sum(item.long_score_delta for item in filters)
        short_score = sum(item.short_score_delta for item in filters)
        adjustment = self._adjustment(regime)
        long_score = clamp(long_score + adjustment[0])
        short_score = clamp(short_score + adjustment[1])
        if long_score >= self.min_score and short_score >= self.min_score and abs(long_score - short_score) <= self.both_gap:
            direction = "BOTH"
        elif long_score >= self.min_score and long_score >= short_score:
            direction = "LONG"
        elif short_score >= self.min_score:
            direction = "SHORT"
        else:
            direction = None
        reasons = [reason for item in filters for reason in item.reasons]
        risks = [risk for item in filters for risk in item.risks]
        return {
            "direction": direction, "long_score": long_score, "short_score": short_score,
            "final_score": max(long_score, short_score), "reasons": reasons, "risks": risks,
            "data_sufficient": (
                not any(item.name == "data_quality" and not item.data_sufficient for item in filters)
                and all(item.data_sufficient for item in filters if item.name in {"trend", "safety"})
            ),
            "components": {item.name: {
                "passed": item.passed, "long_delta": item.long_score_delta,
                "short_delta": item.short_score_delta, "snapshot": item.snapshot,
            } for item in filters},
            "regime_adjustment": {"long": adjustment[0], "short": adjustment[1]},
        }

    @staticmethod
    def _adjustment(regime) -> Tuple[int, int]:
        if regime is None or regime.regime == "UNKNOWN":
            return 0, 0
        mapping = {
            "STRONG_BULL": (10, -5), "BULL": (6, -3), "NEUTRAL": (0, 0),
            "BEAR": (-3, 6), "STRONG_BEAR": (-5, 10),
        }
        return mapping.get(regime.regime, (0, 0))
