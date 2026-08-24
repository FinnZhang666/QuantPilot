import math
from statistics import mean, median


def percentile(values, probability):
    ordered = sorted(float(value) for value in values if value is not None)
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    low, high = int(math.floor(position)), int(math.ceil(position))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def confidence_label(count):
    if count < 30:
        return "LOW"
    if count < 100:
        return "PRELIMINARY"
    if count < 300:
        return "MEDIUM"
    return "HIGH"


def proportion_ci(successes, count, z=1.96):
    if not count:
        return [None, None]
    p = successes / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * count)) / count) / denominator
    return [max(0, center - spread), min(1, center + spread)]


def mean_ci(values, z=1.96):
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return [None, None]
    average = mean(clean)
    if len(clean) < 2:
        return [average, average]
    variance = sum((value - average) ** 2 for value in clean) / (len(clean) - 1)
    spread = z * math.sqrt(variance / len(clean))
    return [average - spread, average + spread]


def summarize(values):
    clean = [float(value) for value in values if value is not None]
    wins = [value for value in clean if value > 0]
    losses = [value for value in clean if value < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        "sample_count": len(clean), "average_return": mean(clean) if clean else None,
        "median_return": median(clean) if clean else None,
        "positive_rate": len(wins) / len(clean) if clean else None,
        "positive_rate_ci_95": proportion_ci(len(wins), len(clean)),
        "average_return_ci_95": mean_ci(clean),
        "p25": percentile(clean, .25), "p75": percentile(clean, .75),
        "maximum_profit": max(clean) if clean else None,
        "maximum_loss": min(clean) if clean else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "expectancy": mean(clean) if clean else None,
        "max_drawdown": min(clean) if clean else None,
        "confidence_level": confidence_label(len(clean)),
    }


def target_stop_path(bars, entry, target_pct, stop_pct, same_bar_policy="STOP_FIRST"):
    target = entry * (1 + target_pct / 100)
    stop = entry * (1 - stop_pct / 100)
    for index, bar in enumerate(bars, 1):
        hit_target, hit_stop = float(bar.high) >= target, float(bar.low) <= stop
        if hit_target and hit_stop:
            winner = same_bar_policy == "TARGET_FIRST"
            return {"outcome": "TARGET" if winner else "STOP", "bars": index,
                    "return_pct": target_pct if winner else -stop_pct, "ambiguous": True}
        if hit_stop:
            return {"outcome": "STOP", "bars": index, "return_pct": -stop_pct, "ambiguous": False}
        if hit_target:
            return {"outcome": "TARGET", "bars": index, "return_pct": target_pct, "ambiguous": False}
    final_return = (float(bars[-1].close) / entry - 1) * 100 if bars else None
    return {"outcome": "TIME_EXIT", "bars": len(bars), "return_pct": final_return, "ambiguous": False}


def trailing_stop_path(bars, entry, trailing_pct):
    peak = entry
    for index, bar in enumerate(bars, 1):
        peak = max(peak, float(bar.high))
        stop = peak * (1 - trailing_pct / 100)
        if float(bar.low) <= stop:
            return {"outcome": "TRAILING_STOP", "bars": index,
                    "return_pct": (stop / entry - 1) * 100}
    return {"outcome": "TIME_EXIT", "bars": len(bars),
            "return_pct": (float(bars[-1].close) / entry - 1) * 100 if bars else None}
