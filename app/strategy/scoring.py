from decimal import Decimal
from typing import Dict, List, Tuple

from app.strategy.constants import FEATURE_ALIASES


def score_components(features: Dict[str, Decimal], parameters: Dict[str, object], relative_name: str) -> Tuple[Dict[str, int], List[str], List[str], Dict[str, bool]]:
    reasons: List[str] = []
    risks: List[str] = []
    ema20 = features[FEATURE_ALIASES["ema20"]]
    ema60 = features[FEATURE_ALIASES["ema60"]]
    slope = features[FEATURE_ALIASES["ema20_slope"]]
    close_ema20 = features[FEATURE_ALIASES["close_vs_ema20"]]
    close_ema60 = features[FEATURE_ALIASES["close_vs_ema60"]]
    distance = features[FEATURE_ALIASES["distance_high20"]]
    return1 = features[FEATURE_ALIASES["return1"]]
    close_position = features[FEATURE_ALIASES["close_position"]]
    body_ratio = features.get(FEATURE_ALIASES["body_ratio"])
    previous_close_ema20 = features.get("_previous_close_vs_ema20")

    trend = 0
    if ema20 > ema60:
        trend += 15
        reasons.append("EMA20高于EMA60")
    if slope > 0:
        trend += 10
        reasons.append("EMA20斜率为正")
    if close_ema60 > 0:
        trend += 5
        reasons.append("收盘价位于EMA60上方")

    pullback_pct = max(Decimal(0), -distance)
    minimum = Decimal(str(parameters["pullback_min_pct"]))
    maximum = Decimal(str(parameters["pullback_max_pct"]))
    pullback_valid = minimum <= pullback_pct <= maximum
    pullback = 25 if pullback_valid else (8 if pullback_pct < minimum else 0)
    if pullback_valid:
        reasons.append("距20周期高点回撤%.2f%%，位于模板范围" % pullback_pct)
    elif pullback_pct < minimum:
        risks.append("回撤不足，当前更接近追高区间")
    else:
        risks.append("回撤超过模板允许范围")

    recovered = close_ema20 > 0 and previous_close_ema20 is not None and previous_close_ema20 <= 0
    recovery = 0
    if close_ema20 > 0:
        recovery += 10
        reasons.append("收盘价位于EMA20上方")
    if return1 > 0:
        recovery += 5
        reasons.append("最新单周期收益为正")
    if close_position >= Decimal(str(parameters["close_position_min"])):
        recovery += 3
        reasons.append("收盘位置较高")
    if body_ratio is not None and body_ratio <= Decimal(str(parameters["body_ratio_max"])):
        recovery += 2
    if not recovered:
        risks.append("尚未确认从EMA20下方重新站回")

    volume_ratio = features.get(FEATURE_ALIASES["volume_ratio20"])
    if volume_ratio is None:
        volume = 0
        risks.append("成交量特征缺失")
    elif volume_ratio >= Decimal(str(parameters["volume_ratio_min"])):
        volume = 10
        reasons.append("成交量达到模板确认标准")
    else:
        volume = max(0, min(9, int(volume_ratio * 10)))
        risks.append("成交量确认不足")

    relative_value = features.get(relative_name) if relative_name else None
    if relative_value is None:
        relative = 0
        risks.append("Benchmark相对强弱特征缺失")
    elif relative_value > Decimal(str(parameters["relative_strength_min"])):
        relative = 10
        reasons.append("相对Benchmark收益为正")
    else:
        relative = 0
        risks.append("相对Benchmark表现偏弱")

    risk = 5
    high_risk = False
    atr_pct = features.get(FEATURE_ALIASES["atr_pct"])
    rsi = features.get(FEATURE_ALIASES["rsi14"])
    vwap = features.get(FEATURE_ALIASES["vwap_distance"])
    if atr_pct is not None and atr_pct > Decimal(str(parameters["atr_pct_max"])):
        risk -= 2
        high_risk = True
        risks.append("ATR百分比高于模板上限")
    if rsi is not None and rsi > Decimal(str(parameters["rsi_overbought"])):
        risk -= 2
        high_risk = True
        risks.append("RSI处于过热区间")
    if vwap is not None and abs(vwap) > Decimal(str(parameters["vwap_deviation_max_pct"])):
        risk -= 1
        risks.append("价格偏离VWAP较大")
    risk = max(0, risk)
    return {
        "trend_score": trend, "pullback_score": pullback,
        "recovery_score": recovery, "volume_score": volume,
        "relative_strength_score": relative, "risk_score": risk,
    }, reasons, risks, {
        "trend_valid": ema20 > ema60,
        "pullback_valid": pullback_valid,
        "pullback_too_deep": pullback_pct > maximum,
        "recovered": recovered,
        "high_risk": high_risk,
        "relative_weak": relative_value is not None and relative_value < 0,
        "relative_confirmed": relative_value is not None and relative_value >= Decimal(str(parameters["relative_strength_min"])),
        "volume_confirmed": volume_ratio is not None and volume_ratio >= Decimal(str(parameters["volume_ratio_min"])),
    }
