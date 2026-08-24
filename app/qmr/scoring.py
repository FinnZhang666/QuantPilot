import math
from statistics import mean, pstdev


def _positive(value, good):
    if value is None:
        return None
    return max(0.0, min(1.0, float(value) / good)) if good else 0.0


def quality_score(fundamental, context, config):
    rules = config["quality_rules"]
    weights = config["weights"]["quality"]
    components = {}
    available = 0.0
    total = 100.0

    def component(name, maximum, parts):
        nonlocal available
        known = [value for value in parts if value is not None]
        coverage = len(known) / len(parts) if parts else 0
        score = maximum * sum(known) / len(known) if known else 0
        available += maximum * coverage
        components[name] = {"score": round(score, 2), "max": maximum, "coverage": round(coverage, 3)}

    f = fundamental
    component("profitability", weights["profitability"], [
        None if f is None or f.net_income_ttm is None else (1 if f.net_income_ttm > 0 else 0),
        None if f is None or f.eps_ttm is None else (1 if f.eps_ttm > 0 else 0),
        None if f is None else _positive(f.operating_margin, rules["operating_margin_good"]),
        None if f is None else _positive(f.roe, rules["roe_good"]),
        None if f is None else _positive(f.roic, rules["roic_good"]),
    ])
    component("growth", weights["growth"], [
        None if f is None else _positive(f.revenue_yoy, rules["growth_good"]),
        None if f is None else _positive(f.eps_yoy, rules["growth_good"]),
        None if f is None else _positive(f.quarterly_trend, rules["growth_good"]),
        None if f is None else _positive(f.forward_earnings_growth, rules["growth_good"]),
    ])
    component("cashflow", weights["cashflow"], [
        None if f is None or f.operating_cash_flow is None else (1 if f.operating_cash_flow > 0 else 0),
        None if f is None or f.free_cash_flow is None else (1 if f.free_cash_flow > 0 else 0),
        None if f is None or f.cash is None or f.debt is None else max(0, min(1, float(f.cash / max(f.debt, 1)))),
        None if f is None or f.debt_to_equity is None else max(0, 1 - float(f.debt_to_equity) / rules["debt_to_equity_high"]),
        None if f is None else _positive(f.interest_coverage, rules["interest_coverage_good"]),
    ])
    component("industry", weights["industry"], [context.get("industry_relative_strength"), None if f is None else _positive(f.sector_profit_trend, rules["growth_good"])])
    weight = max(context.get("qqq_weight") or 0, context.get("spy_weight") or 0)
    component("etf_importance", weights["etf_importance"], [min(1, float(weight) / rules["etf_weight_full"])])
    dollar_volume = context.get("average_dollar_volume")
    liquidity = None if dollar_volume is None else max(0, min(1, (dollar_volume - rules["liquidity_dollar_volume_min"]) / (rules["liquidity_dollar_volume_good"] - rules["liquidity_dollar_volume_min"])))
    component("liquidity", weights["liquidity"], [liquidity])
    coverage = available / total
    # Missing inputs are excluded, never converted to zero. The remaining
    # factor weights are normalized to the original 0-100 scale.
    raw = sum(item["score"] for item in components.values())
    score = round(raw / available * total) if available else 0
    return max(0, min(100, score)), components, coverage


def mispricing_score(prices, benchmark_prices, industry_prices, event, config,
                     valuation_context=None):
    rules = config["mispricing_rules"]
    weights = config["weights"]["mispricing"]
    closes = [float(row.close) for row in prices]
    components = {}
    returns = {}
    points = []
    for days, full in rules["drawdown_full"].items():
        days = int(days)
        value = closes[-1] / closes[-days - 1] - 1 if len(closes) > days else None
        returns[str(days) + "D"] = value
        if value is not None:
            points.append(max(0, min(1, value / float(full))))
    components["multi_period_drawdown"] = round(weights["multi_period_drawdown"] * mean(points), 2) if points else None
    rolling = [closes[i] / closes[i - 5] - 1 for i in range(5, len(closes))]
    current5 = returns.get("5D")
    zscore = None
    percentile = None
    if current5 is not None and len(rolling) >= 20:
        sigma = pstdev(rolling)
        zscore = (current5 - mean(rolling)) / sigma if sigma else 0
        percentile = sum(value <= current5 for value in rolling) / len(rolling)
    anomaly = 0
    if zscore is not None:
        anomaly = max(anomaly, min(1, zscore / rules["zscore_full"]))
    if percentile is not None:
        anomaly = max(anomaly, min(1, rules["percentile_full"] / max(percentile, 1 / len(rolling))))
    components["historical_anomaly"] = round(weights["historical_anomaly"] * anomaly, 2) if zscore is not None or percentile is not None else None

    def latest_return(rows, days=5):
        values = [float(row.close) for row in rows]
        return values[-1] / values[-days - 1] - 1 if len(values) > days else None
    market_return = latest_return(benchmark_prices)
    industry_return = latest_return(industry_prices)
    market_relative = current5 - market_return if current5 is not None and market_return is not None else None
    industry_relative = current5 - industry_return if current5 is not None and industry_return is not None else None
    components["market_relative"] = round(weights["market_relative"] * max(0, min(1, market_relative / rules["relative_full"])), 2) if market_relative is not None else None
    components["industry_relative"] = round(weights["industry_relative"] * max(0, min(1, industry_relative / rules["relative_full"])), 2) if industry_relative is not None else None
    event_factor = rules["event_risk_factors"].get(event.event_risk, 0)
    components["event_risk"] = round(weights["event_risk"] * event_factor, 2) if event.confidence != "LOW" else None
    available_weight = sum(weights[name] for name, value in components.items() if value is not None)
    raw = sum(value for value in components.values() if value is not None)
    score = round(raw * 100 / available_weight) if available_weight else 0
    coverage = available_weight / sum(weights.values())
    valuation = valuation_context or {}
    peer = _valuation_peer_assessment(valuation)
    value_trap = _value_trap_assessment(valuation)
    if peer["score"] is not None:
        blend = float(config.get("valuation_blend_weight", .2))
        score = round(score * (1 - blend) + peer["score"] * blend)
    score = max(0, score - value_trap["deduction"])
    details = {"scores": components, "returns": returns, "zscore_5d": zscore, "percentile_5d": percentile,
               "market_relative_5d": market_relative, "industry_relative_5d": industry_relative,
               "coverage": round(coverage, 4), "available_weight": available_weight,
               "missing_factors": [name for name, value in components.items() if value is None],
               "peer": peer, "value_trap": value_trap}
    return max(0, min(100, score)), details


def _valuation_peer_assessment(context):
    current = context.get("current") or {}
    hierarchy = (("EXPLICIT", context.get("explicit_peers")),
                 ("INDUSTRY", context.get("industry_peers")),
                 ("SECTOR", context.get("sector_peers")),
                 ("MARKET", context.get("market_benchmark")),
                 ("HISTORICAL_SELF", context.get("historical_self")))
    chosen, method = [], "UNAVAILABLE"
    for method, values in hierarchy:
        chosen = values or []
        if chosen:
            break
    metrics = ("trailing_pe", "forward_pe", "peg", "price_to_sales",
               "ev_to_ebitda", "fcf_yield", "earnings_yield")
    factors = []
    for metric in metrics:
        own = current.get(metric)
        peers = [row.get(metric) for row in chosen if row.get(metric) is not None]
        if own is None or not peers:
            continue
        baseline = mean(float(value) for value in peers)
        if metric.endswith("yield"):
            factors.append(max(0, min(1, float(own) / baseline - 1)) if baseline > 0 else 0)
        else:
            factors.append(max(0, min(1, 1 - float(own) / baseline)) if baseline > 0 else 0)
    count = len(chosen)
    confidence = "HIGH" if count >= 10 else "MEDIUM" if count >= 5 else "LOW" if count else "INSUFFICIENT"
    return {"score": round(mean(factors) * 100) if factors else None,
            "peer_count": count, "peer_method": method, "peer_confidence": confidence,
            "factor_coverage": len(factors) / len(metrics)}


def _value_trap_assessment(context):
    f = context.get("fundamentals") or {}
    flags = []
    if f.get("revenue_growth") is not None and f["revenue_growth"] < -.1: flags.append("revenue_deterioration")
    if f.get("margin_change") is not None and f["margin_change"] < -.1: flags.append("margin_collapse")
    if f.get("negative_fcf_periods", 0) >= 3: flags.append("persistent_negative_fcf")
    if f.get("leverage_change") is not None and f["leverage_change"] > .5: flags.append("leverage_deterioration")
    if f.get("earnings_growth") is not None and f["earnings_growth"] < -.25: flags.append("earnings_collapse")
    if f.get("guidance_cuts", 0) >= 2: flags.append("repeated_guidance_cuts")
    if f.get("relative_strength_20d") is not None and f["relative_strength_20d"] < -.2: flags.append("structural_relative_weakness")
    return {"flags": flags, "deduction": min(30, len(flags) * 5)}
