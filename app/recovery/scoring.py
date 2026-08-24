from collections import defaultdict
from statistics import mean


def _clamp(value):
    return max(0.0, min(1.0, value))


def _ema(values, period):
    if not values:
        return None
    alpha = 2.0 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def _ema_series(values, period):
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def _rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0) for change in changes[-period:]]
    losses = [max(-change, 0) for change in changes[-period:]]
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + mean(gains) / avg_loss)


def _atr(rows, period=14):
    if len(rows) < 2:
        return None
    ranges = []
    for previous, current in zip(rows[:-1], rows[1:]):
        high, low, previous_close = float(current.high), float(current.low), float(previous.close)
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(ranges[-period:]) if ranges else None


def _session_rows(rows):
    if not rows:
        return []
    latest = rows[-1]
    trading_date = latest.trading_date
    session = latest.market_session
    return [row for row in rows if row.trading_date == trading_date and row.market_session == session]


def _vwap(rows):
    volume = sum(max(row.volume or 0, 0) for row in rows)
    if volume <= 0:
        return None
    return sum(((float(row.high) + float(row.low) + float(row.close)) / 3) * max(row.volume or 0, 0) for row in rows) / volume


def _higher_low_factor(lows, tolerance):
    if len(lows) < 4:
        return None
    pivots = [lows[i] for i in range(1, len(lows) - 1) if lows[i] <= lows[i - 1] and lows[i] <= lows[i + 1]]
    if len(pivots) < 2:
        midpoint = max(1, len(lows) // 2)
        pivots = [min(lows[:midpoint]), min(lows[midpoint:])]
    first, second = pivots[-2], pivots[-1]
    return _clamp(0.5 + (second / first - 1) / max(tolerance * 4, 1e-9))


def stabilization(rows_by_timeframe, config):
    weights = config["weights"]["stabilization"]
    rules = config["thresholds"]
    samples = defaultdict(list)
    explanations = []
    latest_session = []
    for timeframe, rows in rows_by_timeframe.items():
        session = _session_rows(rows)
        if not session:
            continue
        if timeframe == "5m":
            latest_session = session
        lows = [float(row.low) for row in session]
        closes = [float(row.close) for row in rows]
        current = closes[-1]
        low = min(lows)
        bars_since_low = len(lows) - 1 - max(i for i, value in enumerate(lows) if value == low)
        samples["no_new_low"].append(_clamp(bars_since_low / rules["no_new_low_bars_full"]))
        atr = _atr(rows)
        normalized_recovery = (current - low) / atr if atr and atr > 0 else None
        if normalized_recovery is not None:
            samples["low_recovery"].append(_clamp(normalized_recovery / rules["low_recovery_atr_full"]))
        higher = _higher_low_factor(lows, rules["higher_low_tolerance_pct"])
        if higher is not None:
            samples["higher_low"].append(higher)
        vwap = _vwap(session)
        if vwap:
            above = current >= vwap
            recent_below = any(float(row.low) <= vwap for row in session[-3:])
            samples["vwap_recovery"].append(1.0 if above and recent_below else (0.7 if above else _clamp(current / vwap - 0.98)))
        if len(closes) >= 20:
            ema5, ema10, ema20 = _ema(closes[-20:], 5), _ema(closes[-20:], 10), _ema(closes[-20:], 20)
            trend = 0.0
            if current > ema5: trend += .25
            if ema5 > ema10: trend += .35
            if ema10 > ema20: trend += .40
            samples["short_trend"].append(trend)
    components = {}
    for name, maximum in weights.items():
        factor = mean(samples[name]) if samples[name] else None
        components[name] = {"score": None if factor is None else round(maximum * factor, 2), "max": maximum, "available": factor is not None}
    score = _normalized_score(components)
    if latest_session:
        low = min(float(row.low) for row in latest_session)
        current = float(latest_session[-1].close)
        low_recovery_pct = current / low - 1
        explanations.extend([
            "距本时段低点已过去%s根5分钟K线" % (len(latest_session) - 1 - min(i for i, row in enumerate(latest_session) if float(row.low) == low)),
            "价格从本时段低点修复%.2f%%" % (low_recovery_pct * 100),
        ])
    else:
        low_recovery_pct = 0
    return score, components, low_recovery_pct, explanations


def _same_clock_rvol(rows, session_rows, history_days):
    if not session_rows:
        return None
    latest = session_rows[-1]
    current_volume = sum(max(row.volume or 0, 0) for row in session_rows)
    by_date = defaultdict(list)
    for row in rows:
        if row.trading_date == latest.trading_date or row.market_session != latest.market_session:
            continue
        clock = row.timestamp_market or row.timestamp_utc
        latest_clock = latest.timestamp_market or latest.timestamp_utc
        if (clock.hour, clock.minute) <= (latest_clock.hour, latest_clock.minute):
            by_date[row.trading_date].append(row)
    totals = [sum(max(row.volume or 0, 0) for row in day) for _, day in sorted(by_date.items())[-history_days:]]
    baseline = mean(totals) if totals else 0
    return current_volume / baseline if baseline > 0 else None


def capital_flow(rows, config, active_buy_factor=None):
    weights = config["weights"]["capital_flow"]
    rules = config["thresholds"]
    session = _session_rows(rows)
    components = {}
    reasons = []
    rvol = _same_clock_rvol(rows, session, config["history_days_for_rvol"])
    rvol_factor = None if rvol is None else _clamp((rvol - rules["rvol_start"]) / (rules["rvol_full"] - rules["rvol_start"]))
    components["rvol"] = _component(weights["rvol"], rvol_factor, {"value": rvol})
    up_volume = sum((row.volume or 0) for row in session if float(row.close) >= float(row.open))
    down_volume = sum((row.volume or 0) for row in session if float(row.close) < float(row.open))
    ratio = up_volume / down_volume if down_volume > 0 else (None if up_volume == 0 else rules["up_down_ratio_full"])
    components["up_down_volume"] = _component(weights["up_down_volume"], None if ratio is None else _clamp(ratio / rules["up_down_ratio_full"]), {"ratio": ratio})
    vwap = _vwap(session)
    current = float(session[-1].close) if session else None
    vwap_factor = None if vwap is None or rvol is None or current is None else _clamp((1 if current >= vwap else .2) * max(rvol_factor or 0, .25))
    components["vwap_volume"] = _component(weights["vwap_volume"], vwap_factor, {"vwap": vwap})
    components["active_buy"] = _component(weights["active_buy"], active_buy_factor, {"source": "UNAVAILABLE" if active_buy_factor is None else "PROVIDER"})
    divergence = None
    if len(session) >= 6:
        half = len(session) // 2
        first_low, second_low = min(float(row.low) for row in session[:half]), min(float(row.low) for row in session[half:])
        first_down = sum((row.volume or 0) for row in session[:half] if float(row.close) < float(row.open))
        second_down = sum((row.volume or 0) for row in session[half:] if float(row.close) < float(row.open))
        divergence = .5 * (1 if second_low >= first_low else 0) + .5 * (1 if second_down < first_down else 0)
    components["price_volume_divergence"] = _component(weights["price_volume_divergence"], divergence, {})
    continuity = None
    count = rules["continuity_bars"]
    if len(session) >= count:
        tail = session[-count:]
        continuity = sum(float(row.close) >= float(row.open) and (rvol is None or rvol >= 1) for row in tail) / count
    components["continuity"] = _component(weights["continuity"], continuity, {})
    if rvol is not None: reasons.append("同交易时刻RVOL %.2f" % rvol)
    if ratio is not None: reasons.append("上涨/下跌成交量比 %.2f" % ratio)
    return _normalized_score(components), components, reasons, "PARTIAL" if active_buy_factor is None else "FULL"


def technical(rows, config):
    closes = [float(row.close) for row in rows]
    if len(closes) < 35:
        return None, {"macd": None, "rsi": None}, []
    ema12, ema26 = _ema_series(closes, 12), _ema_series(closes, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26)]
    dea = _ema_series(dif, 9)
    histogram = [line - signal for line, signal in zip(dif, dea)]
    macd_factor = .2 + (.3 if dif[-1] > dea[-1] else 0) + (.25 if histogram[-1] > histogram[-2] else 0) + (.25 if dif[-1] > dif[-2] else 0)
    rsi_now = _rsi(closes)
    rsi_previous = _rsi(closes[:-1])
    rsi_factor = .5 if rsi_now is None else (_clamp(rsi_now / 50) if rsi_previous is None else _clamp(.5 + (rsi_now - rsi_previous) / 10))
    weights = config["weights"]["technical"]
    score = round(100 * (weights["macd"] * macd_factor + weights["rsi"] * rsi_factor) / sum(weights.values()))
    reasons = ["30分钟MACD柱%s" % ("扩大" if histogram[-1] > histogram[-2] else "未扩大"), "RSI %.1f" % rsi_now]
    return score, {"macd": {"dif": dif[-1], "dea": dea[-1], "histogram": histogram[-1], "crossed": dif[-1] > dea[-1], "rising": histogram[-1] > histogram[-2]}, "rsi": {"value": rsi_now, "rising": rsi_previous is not None and rsi_now > rsi_previous}}, reasons


def context_recovery(rows, config):
    session = _session_rows(rows)
    if len(session) < 3:
        return None
    lows = [float(row.low) for row in session]
    current = float(session[-1].close)
    low = min(lows)
    since_low = len(lows) - 1 - max(i for i, value in enumerate(lows) if value == low)
    recovery = current / low - 1
    weights = config["weights"]["context"]
    rules = config["thresholds"]
    return round(100 * (
        weights["no_new_low"] * _clamp(since_low / rules["context_no_new_low_bars_full"]) +
        weights["low_recovery"] * _clamp(recovery / rules["context_low_recovery_full"])
    ) / sum(weights.values()))


def combine(scores, config):
    weights = config["weights"]["recovery"]
    known = [(scores[name], weight) for name, weight in weights.items() if scores.get(name) is not None]
    if not known:
        return 0, 0
    total_weight = sum(weight for _, weight in known)
    return round(sum(score * weight for score, weight in known) / total_weight), total_weight


def stage_and_entry(score, stabilization_score, previous, current_low, config):
    thresholds = config["thresholds"]
    failure = previous is not None and previous.entry_status in ("EARLY_ENTRY", "CONFIRMED_ENTRY", "STRONG_ENTRY") and current_low < float(previous.session_low) * (1 - thresholds["failure_break_pct"])
    if failure:
        return "FAILED_RECOVERY", "FAILED", "重新跌破修复信号前低"
    if score >= thresholds["stage_trend"]:
        stage = "TREND_RECOVERY"
    elif score >= thresholds["stage_confirmed"]:
        stage = "RECOVERY_CONFIRMED"
    elif score >= thresholds["stage_early"]:
        stage = "EARLY_RECOVERY"
    elif score >= thresholds["stage_stabilizing"]:
        stage = "STABILIZING"
    else:
        stage = "PANIC"
    if score >= thresholds["strong_entry"]:
        entry = "STRONG_ENTRY"
    elif score >= thresholds["confirmed_entry"]:
        entry = "CONFIRMED_ENTRY"
    elif score >= thresholds["early_entry"]:
        entry = "EARLY_ENTRY"
    elif score >= thresholds["observe"] or stabilization_score >= thresholds["stage_stabilizing"]:
        entry = "OBSERVE"
    else:
        entry = "WAIT"
    return stage, entry, None


def _component(maximum, factor, detail):
    return dict(detail, score=None if factor is None else round(maximum * factor, 2), max=maximum, available=factor is not None)


def _normalized_score(components):
    known = [item for item in components.values() if item["available"]]
    if not known:
        return 0
    return round(100 * sum(item["score"] for item in known) / sum(item["max"] for item in known))
