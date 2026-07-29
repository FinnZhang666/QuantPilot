from datetime import timezone
from decimal import Decimal
from typing import Dict, List, Optional


HUNDRED = Decimal("100")


def directional_return(entry: Decimal, price: Decimal, direction: str) -> Decimal:
    if entry <= 0:
        raise ValueError("入场参考价格必须大于0。")
    value = (price / entry - Decimal("1")) * HUNDRED
    return value if direction == "LONG" else -value


def calculate_metrics(
    entry: Decimal, bars: List[Dict[str, object]], direction: str,
    target: Optional[Decimal] = None, stop: Optional[Decimal] = None,
) -> Dict[str, object]:
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("方向必须为LONG或SHORT。")
    if not bars:
        raise ValueError("价格路径为空。")
    highs = [Decimal(str(item["high"])) for item in bars]
    lows = [Decimal(str(item["low"])) for item in bars]
    closes = [Decimal(str(item["close"])) for item in bars]
    close_returns = [directional_return(entry, value, direction) for value in closes]
    highest, lowest, last = max(highs), min(lows), closes[-1]
    if direction == "LONG":
        mfe = directional_return(entry, highest, direction)
        mae = directional_return(entry, lowest, direction)
        target_hit = target is not None and highest >= target
        stop_hit = stop is not None and lowest <= stop
    else:
        mfe = directional_return(entry, lowest, direction)
        mae = directional_return(entry, highest, direction)
        target_hit = target is not None and lowest <= target
        stop_hit = stop is not None and highest >= stop
    started = _aware(bars[0]["timestamp"])
    finished = _aware(bars[-1]["timestamp"])
    seconds = max(0, int((finished - started).total_seconds()))
    return {
        "last_price": last, "exit_price": last,
        "return_percent": directional_return(entry, last, direction),
        "mfe_percent": max(Decimal("0"), mfe),
        "mae_percent": min(Decimal("0"), mae),
        "max_close_return": max(close_returns),
        "min_close_return": min(close_returns),
        "highest_price": highest, "lowest_price": lowest,
        "target_hit": target_hit, "stop_hit": stop_hit,
        "holding_bars": len(bars), "holding_seconds": seconds,
        "holding_minutes": seconds // 60,
        "holding_days": Decimal(seconds) / Decimal("86400"),
    }


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
