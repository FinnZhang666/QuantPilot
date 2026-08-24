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
        score = maximum * sum(known) / len(parts) if parts else 0
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
    score = round(sum(item["score"] for item in components.values()))
    coverage = available / total
    return max(0, min(100, score)), components, coverage


def mispricing_score(prices, benchmark_prices, industry_prices, event, config):
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
    components["multi_period_drawdown"] = round(weights["multi_period_drawdown"] * mean(points), 2) if points else 0
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
    components["historical_anomaly"] = round(weights["historical_anomaly"] * anomaly, 2)

    def latest_return(rows, days=5):
        values = [float(row.close) for row in rows]
        return values[-1] / values[-days - 1] - 1 if len(values) > days else None
    market_return = latest_return(benchmark_prices)
    industry_return = latest_return(industry_prices)
    market_relative = current5 - market_return if current5 is not None and market_return is not None else None
    industry_relative = current5 - industry_return if current5 is not None and industry_return is not None else None
    components["market_relative"] = round(weights["market_relative"] * max(0, min(1, market_relative / rules["relative_full"])), 2) if market_relative is not None else 0
    components["industry_relative"] = round(weights["industry_relative"] * max(0, min(1, industry_relative / rules["relative_full"])), 2) if industry_relative is not None else 0
    event_factor = rules["event_risk_factors"].get(event.event_risk, 0)
    components["event_risk"] = round(weights["event_risk"] * event_factor, 2)
    score = round(sum(components.values()))
    details = {"scores": components, "returns": returns, "zscore_5d": zscore, "percentile_5d": percentile,
               "market_relative_5d": market_relative, "industry_relative_5d": industry_relative}
    return max(0, min(100, score)), details
