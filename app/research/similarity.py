from decimal import Decimal


def similarity_score(current, other, current_review=None, other_review=None):
    score = Decimal("0")
    if current.direction == other.direction:
        score += Decimal("30")
    if current.strategy_name == other.strategy_name:
        score += Decimal("25")
    if current.timeframe == other.timeframe:
        score += Decimal("15")
    if current.market_regime and current.market_regime == other.market_regime:
        score += Decimal("10")
    score += _closeness(current.score, other.score, Decimal("10"))
    score += _closeness(current.confidence, other.confidence, Decimal("5"))
    if current_review and other_review:
        score += _closeness(
            current_review.return_percent, other_review.return_percent, Decimal("5"),
        )
    return round(float(min(Decimal("100"), score)), 2)


def _closeness(left, right, weight):
    if left is None or right is None:
        return Decimal("0")
    distance = min(Decimal("100"), abs(Decimal(str(left)) - Decimal(str(right))))
    return weight * (Decimal("1") - distance / Decimal("100"))
