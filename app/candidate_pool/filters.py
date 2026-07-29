from typing import Dict, List

from app.candidate_pool.models import FilterResult


def _number(features, name):
    value = features.get(name)
    return float(value) if value is not None else None


def evaluate_filters(features: Dict[str, object], config: Dict[str, object], watchlist: bool) -> List[FilterResult]:
    required = ("close_vs_ema20_pct", "ema20_vs_ema60_pct", "ema20_slope_5")
    missing = [name for name in required if features.get(name) is None]
    if missing:
        return [FilterResult(
            "data_quality", False, 0, 0, [],
            ["缺少必要特征：" + "、".join(missing)], False, {"missing": missing},
        )]
    results = []
    close_ema = _number(features, "close_vs_ema20_pct")
    ema_spread = _number(features, "ema20_vs_ema60_pct")
    slope = _number(features, "ema20_slope_5")
    long_trend = close_ema > 0 and ema_spread > 0 and slope > 0
    short_trend = close_ema < 0 and ema_spread < 0 and slope < 0
    results.append(FilterResult(
        "trend", long_trend or short_trend, 25 if long_trend else 0,
        25 if short_trend else 0,
        (["中期上涨趋势成立"] if long_trend else []) + (["中期下跌趋势成立"] if short_trend else []),
        [] if long_trend or short_trend else ["趋势结构混合"], True,
        {"close_vs_ema20_pct": close_ema, "ema20_vs_ema60_pct": ema_spread, "ema20_slope_5": slope},
    ))
    high = _number(features, "breakout_high_20_pct")
    low = _number(features, "distance_from_low_20_pct")
    near_high = high is not None and high >= float(config["thresholds"]["near_breakout_pct"])
    near_low = low is not None and low <= float(config["thresholds"]["near_breakdown_pct"])
    results.append(FilterResult(
        "breakout_breakdown", near_high or near_low, 20 if near_high else 0, 20 if near_low else 0,
        (["接近或突破20周期高点"] if near_high else []) + (["接近或跌破20周期低点"] if near_low else []),
        [], high is not None or low is not None, {"breakout_high_20_pct": high, "distance_from_low_20_pct": low},
    ))
    relative = _number(features, "relative_return_qqq_20")
    results.append(FilterResult(
        "relative_strength", relative is not None,
        15 if relative is not None and relative > 0 else 0,
        15 if relative is not None and relative < 0 else 0,
        ["相对强弱可用"] if relative is not None else [],
        [] if relative is not None else ["相对基准特征缺失"],
        relative is not None, {"relative_return": relative},
    ))
    ratio = _number(features, "volume_ratio_20")
    ret = _number(features, "return_1")
    confirmed = ratio is not None and ratio >= float(config["thresholds"]["volume_confirm"])
    results.append(FilterResult(
        "volume", confirmed, 10 if confirmed and (ret or 0) > 0 else 0,
        10 if confirmed and (ret or 0) < 0 else 0,
        ["成交量异常并具有方向"] if confirmed else [],
        [] if ratio is not None else ["成交量比率缺失"], ratio is not None,
        {"volume_ratio_20": ratio, "return_1": ret},
    ))
    atr = _number(features, "atr_pct_14")
    safe = atr is not None and atr <= float(config["thresholds"]["extreme_atr_pct"])
    results.append(FilterResult(
        "safety", safe, 20 if safe else 0, 20 if safe else 0,
        ["波动率处于允许范围"] if safe else [],
        [] if safe else ["波动率过高或数据缺失"], atr is not None,
        {"atr_pct_14": atr},
    ))
    results.append(FilterResult(
        "watchlist_priority", watchlist, 10 if watchlist else 0, 10 if watchlist else 0,
        ["Watchlist优先级加分"] if watchlist else [], [], True, {"watchlist": watchlist},
    ))
    return results
