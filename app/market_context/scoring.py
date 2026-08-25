"""Deterministic global/sector context scoring with no external calls."""


HORIZONS = (1, 3, 5, 10, 20)


def clamp(value):
    return max(0, min(100, int(round(value))))


def returns(closes):
    if not closes:
        return {day: None for day in HORIZONS}
    current = float(closes[-1])
    return {day: (current / float(closes[-day - 1]) - 1) if len(closes) > day else None
            for day in HORIZONS}


def asset_score(closes, inverse, horizon_weights):
    values = returns(closes)
    present = [(day, value) for day, value in values.items() if value is not None]
    if not present:
        return None, values
    score = 50.0
    for day, value in present:
        direction = -1 if inverse else 1
        weight = horizon_weights.get(day, horizon_weights.get(str(day), 0))
        score += direction * max(-1, min(1, value / 0.06)) * 50 * float(weight)
    if len(closes) >= 20:
        average = sum(float(value) for value in closes[-20:]) / 20
        score += (8 if float(closes[-1]) >= average else -8) * (-1 if inverse else 1)
    return clamp(score), values


def global_score(series, config):
    assets, weighted, available_weight, details = config["assets"], 0.0, 0.0, {}
    for symbol, rules in assets.items():
        score, periods = asset_score(series.get(symbol, []), rules["inverse"], config["horizons"])
        details[symbol] = {"score": score, "returns": periods,
                           "data_available": score is not None}
        if score is not None:
            weight = float(rules["weight"])
            weighted += score * weight
            available_weight += weight
    score = clamp(weighted / available_weight) if available_weight else 50
    thresholds = config["states"]
    state = ("RISK_ON" if score >= thresholds["risk_on"] else
             "NEUTRAL" if score >= thresholds["neutral"] else
             "CAUTION" if score >= thresholds["caution"] else "RISK_OFF")
    coverage = round(available_weight / sum(float(row["weight"]) for row in assets.values()), 4)
    return {"global_score": score, "global_state": state, "asset_scores": details,
            "coverage": coverage, "data_sufficient": coverage >= config["minimum_coverage"]}


def sector_score(sector_closes, spy_closes, qqq_closes, breadth, states):
    periods = returns(sector_closes)
    spy, qqq = returns(spy_closes), returns(qqq_closes)
    relative = {day: None if periods[day] is None else periods[day] - (
        qqq[day] if qqq[day] is not None else spy[day] if spy[day] is not None else 0)
        for day in HORIZONS}
    present = [value for value in relative.values() if value is not None]
    momentum = [value for value in periods.values() if value is not None]
    score = 50
    if present:
        score += max(-25, min(25, sum(present) / len(present) * 500))
    if momentum:
        score += max(-15, min(15, sum(momentum) / len(momentum) * 300))
    if breadth is not None:
        score += (float(breadth) - .5) * 20
    score = clamp(score)
    state = ("STRONG" if score >= states["strong"] else
             "POSITIVE" if score >= states["positive"] else
             "NEUTRAL" if score >= states["neutral"] else
             "WEAK" if score >= states["weak"] else "VERY_WEAK")
    rotation = clamp(50 + (relative.get(5) or 0) * 700 + (relative.get(20) or 0) * 300)
    return {"sector_score": score, "sector_state": state, "relative": relative,
            "returns": periods, "breadth": breadth, "rotation_score": rotation}
