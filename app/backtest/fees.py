from decimal import Decimal


def commission(shares: int, per_trade: Decimal, per_share: Decimal, minimum: Decimal) -> Decimal:
    return max(per_trade + per_share * shares, minimum)


def adjusted_price(raw_price: Decimal, slippage_bps: Decimal, is_buy: bool) -> Decimal:
    multiplier = Decimal("1") + (slippage_bps / Decimal("10000")) * (1 if is_buy else -1)
    return raw_price * multiplier
