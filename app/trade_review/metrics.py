from decimal import Decimal
from typing import Dict, Iterable, Optional


HUNDRED = Decimal("100")


def calculate_excursions(
    entry_price, bars: Iterable[object], direction: str,
    target_price: Optional[object] = None, stop_price: Optional[object] = None,
) -> Dict[str, object]:
    entry = Decimal(str(entry_price))
    if entry <= 0 or direction not in ("LONG", "SHORT"):
        raise ValueError("复盘Entry Price或Direction无效。")
    items = list(bars)
    if not items:
        raise ValueError("复盘区间没有可用历史K线。")
    high = max(Decimal(str(item.high)) for item in items)
    low = min(Decimal(str(item.low)) for item in items)
    target = Decimal(str(target_price)) if target_price is not None else None
    stop = Decimal(str(stop_price)) if stop_price is not None else None
    if direction == "LONG":
        mfe = (high / entry - Decimal("1")) * HUNDRED
        mae = (low / entry - Decimal("1")) * HUNDRED
        target_hit = target is not None and high >= target
        stop_hit = stop is not None and low <= stop
    else:
        mfe = (Decimal("1") - low / entry) * HUNDRED
        mae = (Decimal("1") - high / entry) * HUNDRED
        target_hit = target is not None and low <= target
        stop_hit = stop is not None and high >= stop
    return {
        "mfe": max(Decimal("0"), mfe), "mae": min(Decimal("0"), mae),
        "target_hit": target_hit, "stop_hit": stop_hit,
    }


def classify_result(entry_price, exit_price, direction: str) -> str:
    entry, exit_value = Decimal(str(entry_price)), Decimal(str(exit_price))
    delta = exit_value - entry if direction == "LONG" else entry - exit_value
    return "WIN" if delta > 0 else "LOSS" if delta < 0 else "BREAKEVEN"
