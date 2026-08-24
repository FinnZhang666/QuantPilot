from math import sqrt
from statistics import mean


STATES = ("HOLD", "WATCH", "PROTECT", "REDUCE", "EXIT")
FLOW_FIELDS = (
    "super_large_inflow", "super_large_outflow", "super_large_net",
    "large_inflow", "large_outflow", "large_net",
    "medium_inflow", "medium_outflow", "medium_net",
    "small_inflow", "small_outflow", "small_net",
    "total_inflow", "total_outflow", "total_net", "total_turnover",
)


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))


def _number(data, key):
    value = (data or {}).get(key)
    return None if value is None else float(value)


def evaluate_money_flow(raw, price=None, history=None, config=None):
    """Classify order-size proxies; never claims the actor is a real institution."""
    config = config or {}
    price = price or {}
    history = history or []
    required = ("super_large_net", "large_net", "medium_net", "small_net", "total_turnover")
    if not raw or any(_number(raw, key) is None for key in required):
        return {"data_available": False, "data_status": "UNAVAILABLE", "coverage": 0,
                "confidence": "INSUFFICIENT", "regime": "UNKNOWN", "money_flow_score": None,
                "accumulation_score": None, "distribution_score": None,
                "absorption_score": None, "institutional_net": None, "retail_net": None,
                "institutional_share": None, "retail_share": None, "rolling": {}}
    turnover = abs(_number(raw, "total_turnover"))
    if turnover <= 0:
        return {"data_available": False, "data_status": "UNAVAILABLE", "coverage": 0,
                "confidence": "INSUFFICIENT", "regime": "UNKNOWN", "money_flow_score": None,
                "accumulation_score": None, "distribution_score": None,
                "absorption_score": None, "institutional_net": None, "retail_net": None,
                "institutional_share": None, "retail_share": None, "rolling": {},
                "error": "total_turnover_zero"}
    institutional = _number(raw, "super_large_net") + _number(raw, "large_net")
    retail = _number(raw, "small_net")
    medium = _number(raw, "medium_net")
    institutional_share, retail_share = institutional / turnover, retail / turnover
    threshold = float(config.get("share_threshold", .002))
    strong = float(config.get("strong_share_threshold", .006))
    neutral = float(config.get("neutral_share_band", .0015))
    holds = bool(price.get("rejected_lower") or price.get("higher_low") or price.get("vwap_reclaimed"))
    high_stall = bool(price.get("high_stall") or price.get("upper_rejection"))
    accumulation = clamp(50 * max(0, institutional_share) / strong +
                         30 * max(0, -retail_share) / strong + 20 * holds)
    distribution = clamp(50 * max(0, -institutional_share) / strong +
                         30 * max(0, retail_share) / strong + 20 * high_stall)
    absorption = clamp(45 * max(0, -retail_share) / strong +
                       25 * (abs(institutional_share) <= neutral or institutional_share > -threshold) +
                       30 * holds)
    all_positive = institutional_share > threshold and retail_share > threshold and medium > 0
    all_negative = institutional_share < -threshold and retail_share < -threshold and medium < 0
    if all_positive:
        regime = "BROAD_BUYING"
    elif all_negative:
        regime = "BROAD_SELLING"
    elif absorption >= 65 and institutional_share <= threshold:
        regime = "POSSIBLE_ABSORPTION"
    elif accumulation >= 60 and accumulation > distribution:
        regime = "ACCUMULATION"
    elif distribution >= 60:
        regime = "DISTRIBUTION"
    else:
        regime = "NEUTRAL"
    rolling = _rolling_flow(history + [raw], config.get("rolling_windows", [1, 3, 5, 10]))
    continuity = rolling.get("3D", {}).get("institutional_share")
    if continuity is not None:
        distribution = clamp(distribution + max(0, -continuity / strong) * 15)
        accumulation = clamp(accumulation + max(0, continuity / strong) * 15)
    risk = max(distribution, 85 if regime == "BROAD_SELLING" else 0)
    if regime in {"ACCUMULATION", "POSSIBLE_ABSORPTION", "BROAD_BUYING"}:
        risk = max(0, risk - max(accumulation, absorption) * .35)
    coverage = sum(_number(raw, key) is not None for key in FLOW_FIELDS) / len(FLOW_FIELDS)
    minimum = float(config.get("minimum_regime_coverage", .75))
    if coverage < minimum:
        regime = "UNKNOWN"
    return {"data_available": True, "data_status": "AVAILABLE" if coverage == 1 else "PARTIAL",
            "coverage": coverage, "confidence": "HIGH" if coverage >= .8 else "MEDIUM",
            "regime": regime, "money_flow_score": round(clamp(risk), 2),
            "accumulation_score": round(accumulation, 2), "distribution_score": round(distribution, 2),
            "absorption_score": round(absorption, 2), "institutional_net": institutional,
            "retail_net": retail, "institutional_share": institutional_share,
            "retail_share": retail_share, "rolling": rolling}


def _rolling_flow(rows, windows):
    output = {}
    for window in windows:
        sample = rows[-int(window):]
        turnover = sum(abs(float(row.get("total_turnover") or 0)) for row in sample)
        institutional = sum(float(row.get("super_large_net") or 0) + float(row.get("large_net") or 0)
                            for row in sample)
        retail = sum(float(row.get("small_net") or 0) for row in sample)
        output["%sD" % window] = {"institutional_net": institutional, "retail_net": retail,
            "institutional_share": institutional / turnover if turnover else None,
            "retail_share": retail / turnover if turnover else None, "sample_count": len(sample)}
    return output


def _closes(rows):
    return [float(row.close if hasattr(row, "close") else row["close"]) for row in rows]


def _values(rows, key):
    return [float(getattr(row, key) if hasattr(row, key) else row[key]) for row in rows]


def ema(values, period):
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def atr(rows, period=14):
    if len(rows) < 2:
        return None
    highs, lows, closes = _values(rows, "high"), _values(rows, "low"), _closes(rows)
    tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
          for i in range(1, len(rows))]
    return mean(tr[-period:]) if tr else None


def rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(value, 0) for value in changes[-period:]]
    losses = [max(-value, 0) for value in changes[-period:]]
    average_gain, average_loss = mean(gains), mean(losses)
    if average_loss == 0:
        return 100.0
    return 100 - 100 / (1 + average_gain / average_loss)


def kdj(rows, period=9):
    if len(rows) < period:
        return None
    highs, lows, closes = _values(rows, "high"), _values(rows, "low"), _closes(rows)
    k = d = 50.0
    history = []
    for index in range(period - 1, len(rows)):
        high = max(highs[index - period + 1:index + 1])
        low = min(lows[index - period + 1:index + 1])
        rsv = 50.0 if high == low else (closes[index] - low) / (high - low) * 100
        k, d = (2 * k + rsv) / 3, (2 * d + k) / 3
        history.append((k, d, 3 * k - 2 * d))
    return history[-1] if history else None


def dmi(rows, period=14):
    if len(rows) <= period:
        return None
    highs, lows, closes = _values(rows, "high"), _values(rows, "low"), _closes(rows)
    plus_dm, minus_dm, true_ranges = [], [], []
    for index in range(1, len(rows)):
        up, down = highs[index] - highs[index - 1], lows[index - 1] - lows[index]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        true_ranges.append(max(highs[index] - lows[index], abs(highs[index] - closes[index - 1]),
                               abs(lows[index] - closes[index - 1])))
    tr = sum(true_ranges[-period:])
    if tr <= 0:
        return None
    plus_di = 100 * sum(plus_dm[-period:]) / tr
    minus_di = 100 * sum(minus_dm[-period:]) / tr
    adx_proxy = 100 * abs(plus_di - minus_di) / max(plus_di + minus_di, 1e-9)
    return plus_di, minus_di, adx_proxy


def _trend_risk(rows):
    values = _closes(rows)
    if len(values) < 20:
        return None, ["trend_data_insufficient"]
    e5, e10, e20, e50 = ema(values, 5), ema(values, 10), ema(values, 20), ema(values, 50)
    e12, e26 = ema(values, 12), ema(values, 26)
    macd = [a - b for a, b in zip(e12, e26)]
    signal = ema(macd, 9)
    histogram = [a - b for a, b in zip(macd, signal)]
    risk, reasons = 0.0, []
    if values[-1] < e5[-1]: risk += 15; reasons.append("price_below_ema5")
    if values[-1] < e10[-1]: risk += 15; reasons.append("price_below_ema10")
    if values[-1] < e20[-1]: risk += 25; reasons.append("price_below_ema20")
    if len(values) >= 50 and values[-1] < e50[-1]: risk += 10; reasons.append("price_below_ema50")
    if macd[-1] < signal[-1]: risk += 20; reasons.append("macd_below_signal")
    if len(histogram) >= 3 and histogram[-1] < histogram[-2] < histogram[-3]:
        risk += 15; reasons.append("macd_histogram_weakening")
    if len(values) >= 6 and max(values[-3:]) < max(values[-6:-3]):
        risk += 10; reasons.append("lower_rebound_high")
    current_rsi = rsi(values)
    oscillator = kdj(rows)
    directional = dmi(rows)
    # Oscillators are confirmation only and never sufficient for EXIT.
    if current_rsi is not None and current_rsi >= 70 and values[-1] < values[-2]:
        risk += 5; reasons.append("rsi_overheated_and_turning")
    if oscillator is not None and oscillator[0] < oscillator[1] and oscillator[2] >= 70:
        risk += 5; reasons.append("kdj_high_level_weakening")
    if directional is not None and directional[1] > directional[0] and directional[2] >= 25:
        risk += 10; reasons.append("negative_dmi_trend")
    return clamp(risk), reasons


def trend_risk(timeframes, weights):
    scored, reasons, used = 0.0, [], 0.0
    details = {}
    for timeframe, weight in weights.items():
        score, why = _trend_risk(timeframes.get(timeframe, []))
        details[timeframe] = score
        if score is not None:
            scored += score * float(weight); used += float(weight)
            reasons.extend("%s_%s" % (timeframe, value) for value in why)
    return (round(scored / used, 2) if used else None), reasons, details


def _return(rows, window):
    values = _closes(rows)
    return values[-1] / values[-window - 1] - 1 if len(values) > window else None


def relative_strength_risk(stock, benchmarks, sector, windows, full=-.10):
    points, details = [], {}
    for window in windows:
        own = _return(stock, window)
        values = []
        for name, rows in benchmarks.items():
            value = _return(rows, window)
            if own is not None and value is not None:
                values.append(own - value); details["%s_%sD" % (name, window)] = own - value
        sector_value = _return(sector, window) if sector else None
        if own is not None and sector_value is not None:
            values.append(own - sector_value); details["sector_%sD" % window] = own - sector_value
        points.extend(values)
    if not points:
        return None, [], details
    negative = [clamp(value / full * 100) for value in points if value < 0]
    score = mean(negative) if negative else 0
    reasons = ["relative_strength_deteriorating"] if score >= 35 else []
    return round(score, 2), reasons, details


def sector_rotation_risk(current_sector, sectors, windows, rank_drop_full=3):
    if not current_sector or current_sector not in sectors or len(sectors) < 2:
        return None, [], {}
    ranks, details = [], {}
    for window in windows:
        returns = {name: _return(rows, window) for name, rows in sectors.items()}
        valid = {name: value for name, value in returns.items() if value is not None}
        if current_sector not in valid:
            continue
        ordered = sorted(valid, key=valid.get, reverse=True)
        rank = ordered.index(current_sector) + 1
        ranks.append(rank); details["%sD" % window] = {"rank": rank, "returns": valid}
    if not ranks:
        return None, [], details
    average_rank = mean(ranks)
    score = clamp((average_rank - 1) / max(float(rank_drop_full), 1) * 100)
    deteriorating = len(ranks) >= 2 and ranks[-1] > ranks[0]
    if deteriorating: score = clamp(score + 15)
    return round(score, 2), (["sector_relative_rank_deteriorating"] if score >= 35 else []), details


def profit_protection(entry, highest, current, current_atr, config):
    entry, highest, current = float(entry), float(highest), float(current)
    current_return = (current / entry - 1) * 100
    max_return = (highest / entry - 1) * 100
    giveback = max(0, max_return - current_return)
    protect = config["profit_stages"]
    risk, reasons = 0.0, []
    if giveback >= protect["giveback_protect"]: risk += 45; reasons.append("profit_giveback_protect")
    if giveback >= protect["giveback_reduce"]: risk += 30; reasons.append("profit_giveback_reduce")
    if giveback >= protect["giveback_exit"]: risk += 25; reasons.append("profit_giveback_severe")
    atr_pct = (float(current_atr) / current * 100) if current_atr and current else None
    trailing_distance = (atr_pct * float(protect["atr_multiple"])) if atr_pct is not None else None
    return clamp(risk), reasons, {"current_return": current_return, "max_return": max_return,
        "profit_giveback": giveback, "atr_pct": atr_pct, "trailing_distance_pct": trailing_distance}


def exhaustion_risk(rows, flow=None):
    if len(rows) < 20:
        return None, [], {}
    opens, highs, lows, closes, volumes = (_values(rows, key) for key in ("open", "high", "low", "close", "volume"))
    latest_range = max(highs[-1] - lows[-1], 1e-9)
    upper_wick = (highs[-1] - max(opens[-1], closes[-1])) / latest_range
    volume_ratio = volumes[-1] / max(mean(volumes[-20:-1]), 1)
    stall = closes[-1] <= closes[-2] * 1.002 and volume_ratio >= 1.5
    fast_rise = closes[-2] / closes[-6] - 1 if len(closes) >= 6 else 0
    risk, reasons = 0.0, []
    if upper_wick >= .45: risk += 30; reasons.append("long_upper_wick")
    if stall: risk += 30; reasons.append("high_volume_stall")
    if fast_rise >= .15 and closes[-1] < opens[-1]: risk += 20; reasons.append("rapid_rise_rejection")
    if flow and flow.get("regime") == "DISTRIBUTION": risk += 20; reasons.append("price_flow_distribution")
    return clamp(risk), reasons, {"upper_wick_ratio": upper_wick, "volume_ratio": volume_ratio,
        "five_bar_return": fast_rise}


def dynamic_support(rows, config):
    if len(rows) < 5:
        return None, "UNKNOWN", None
    window = int(config["trend"]["support_window"])
    lows, closes = _values(rows[-window:], "low"), _closes(rows)
    current_atr = atr(rows)
    swing = min(lows)
    e20 = ema(closes, 20)[-1]
    support = max(swing, e20 - (current_atr or 0) * float(config["trend"]["support_atr_buffer"]))
    close = closes[-1]
    status = "BROKEN" if close < support else ("TESTING" if close <= support + (current_atr or 0) else "HEALTHY")
    return support, status, current_atr


def evaluate_exit(entry, highest, current, timeframes, benchmarks, sector_rows,
                  sector_universe, money_flow, config, previous_state="HOLD",
                  fundamental_invalid=False, portfolio_risk=False):
    daily = timeframes.get("1d", [])
    support, support_status, current_atr = dynamic_support(daily, config)
    trend, trend_reasons, trend_details = trend_risk(timeframes, config["trend"]["timeframe_weights"])
    rs, rs_reasons, rs_details = relative_strength_risk(
        daily, benchmarks, sector_rows, config["relative_strength"]["windows"],
        float(config["relative_strength"]["deterioration_full"]))
    rotation, rotation_reasons, rotation_details = sector_rotation_risk(
        next((key for key, value in sector_universe.items() if value is sector_rows), None),
        sector_universe, config["sector_rotation"]["windows"],
        config["sector_rotation"]["rank_drop_full"])
    profit, profit_reasons, profit_details = profit_protection(entry, highest, current, current_atr, config)
    exhaustion, exhaustion_reasons, exhaustion_details = exhaustion_risk(daily, money_flow)
    flow_risk = money_flow.get("money_flow_score") if money_flow else None
    reasons = trend_reasons + rs_reasons + rotation_reasons + profit_reasons + exhaustion_reasons
    if money_flow and money_flow.get("regime") == "DISTRIBUTION": reasons.append("money_flow_possible_distribution")
    if money_flow and money_flow.get("regime") == "BROAD_SELLING": reasons.append("money_flow_broad_selling")
    components = {"capital_flow": flow_risk, "trend": trend, "relative_strength": rs,
        "sector_rotation": rotation, "profit_protection": profit, "exhaustion": exhaustion}
    weighted, available = 0.0, 0.0
    for name, value in components.items():
        weight = float(config["weights"][name])
        if value is not None:
            weighted += float(value) * weight; available += weight
    score = round(weighted / available, 2) if available else 0.0
    confidence = round(available, 2)
    hard_reason = None
    if fundamental_invalid: hard_reason = "qmr_fundamental_thesis_invalidated"
    elif portfolio_risk: hard_reason = "paper_portfolio_risk_limit"
    elif support_status == "BROKEN" and current_atr and float(current) < float(support) - current_atr * float(config["hard_exit"]["support_break_atr"]):
        hard_reason = "dynamic_support_effectively_broken"
    elif score >= float(config["hard_exit"]["maximum_risk_score"]): hard_reason = "maximum_exit_risk"
    thresholds = config["state_thresholds"]
    if hard_reason or score >= thresholds["exit"]: state = "EXIT"
    elif score >= thresholds["reduce"]: state = "REDUCE"
    elif score >= thresholds["protect"]: state = "PROTECT"
    elif score >= thresholds["watch"]: state = "WATCH"
    else: state = "HOLD"
    ratio = None
    if state == "REDUCE":
        elevated = score >= config["reduce"]["elevated_score"] or (
            flow_risk is not None and flow_risk >= 70 and trend is not None and trend >= 60)
        ratio = config["reduce"]["elevated_ratio"] if elevated else config["reduce"]["default_ratio"]
    if hard_reason: reasons.insert(0, hard_reason)
    return {"exit_risk_score": score, "state": state, "previous_state": previous_state,
        "reduce_ratio": ratio, "hard_exit_reason": hard_reason,
        "exit_reason": hard_reason or (reasons[0] if reasons else None), "reasons": list(dict.fromkeys(reasons)),
        "confidence": confidence, "dynamic_support": support, "support_status": support_status,
        "components": components, "details": {"trend": trend_details, "relative_strength": rs_details,
            "sector_rotation": rotation_details, "profit_protection": profit_details,
            "exhaustion": exhaustion_details, "money_flow": money_flow or {"data_available": False}}}
