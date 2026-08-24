from datetime import timedelta


STATUS_ORDER = {"REJECT": -1, "WAIT": 0, "WATCH": 1, "EARLY_ENTRY": 2, "CONFIRMED_ENTRY": 3, "STRONG_ENTRY": 4}
CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _bounded(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def grade(score, config):
    for name, minimum in sorted(config["grades"].items(), key=lambda item: item[1], reverse=True):
        if score >= minimum:
            return name
    return "D"


def base_status(score, config):
    thresholds = config["status_thresholds"]
    if score >= thresholds["strong_entry"]: return "STRONG_ENTRY"
    if score >= thresholds["confirmed_entry"]: return "CONFIRMED_ENTRY"
    if score >= thresholds["early_entry"]: return "EARLY_ENTRY"
    if score >= thresholds["watch"]: return "WATCH"
    return "WAIT"


def chase_risk(current_price, recovery_signal_price, config):
    if not recovery_signal_price or recovery_signal_price <= 0:
        return 0, "UNKNOWN", None
    advance = current_price / recovery_signal_price - 1
    rules = config["chase"]
    factor = _bounded((advance - rules["start_pct"]) / (rules["full_pct"] - rules["start_pct"]), 0, 1)
    score = round(100 * factor)
    return score, "HIGH" if score >= rules["high_score"] else ("MEDIUM" if score > 0 else "LOW"), advance


def calculate(inputs, config, previous=None, evaluation_time=None):
    weights = config["weights"]
    source_scores = {
        "quality": inputs["quality_score"], "mispricing": inputs["mispricing_score"],
        "recovery": inputs["recovery_score"], "sector": inputs.get("sector_score"),
        "market": inputs.get("market_score"), "etf_importance": inputs.get("etf_importance_score"),
    }
    available = [(float(score), weights[name]) for name, score in source_scores.items() if score is not None]
    raw = round(sum(score * weight for score, weight in available) / sum(weight for _, weight in available)) if available else 0
    risk_rules = config["risk"]
    risk = {}
    hard_reject = inputs["fundamental_risk"] == "HIGH"
    risk["fundamental"] = {"penalty": 0, "hard_reject": hard_reject, "value": inputs["fundamental_risk"]}
    market_penalty = risk_rules["market_panic_penalty"] if inputs.get("market_state") in ("MARKET_PANIC", "SYSTEMIC_PANIC") else 0
    risk["market_panic"] = {"penalty": market_penalty, "value": inputs.get("market_state")}
    sector = inputs.get("sector_score")
    sector_penalty = 0 if sector is None or sector >= risk_rules["sector_minimum"] else round(risk_rules["sector_maximum_penalty"] * (risk_rules["sector_minimum"] - sector) / risk_rules["sector_minimum"])
    risk["sector"] = {"penalty": sector_penalty, "value": sector}
    failed_penalty = risk_rules["failed_recovery_penalty"] if inputs["recovery_stage"] == "FAILED_RECOVERY" else 0
    risk["failed_recovery"] = {"penalty": failed_penalty, "value": inputs["recovery_stage"]}
    confidence = inputs["data_confidence"]
    confidence_penalty = risk_rules["low_confidence_penalty"] if confidence == "LOW" else (risk_rules["medium_confidence_penalty"] if confidence == "MEDIUM" else 0)
    risk["data_confidence"] = {"penalty": confidence_penalty, "value": confidence}
    volatility_penalty = 0
    volatility = inputs.get("volatility", {})
    known_volatility = 0
    volatility_fields = (("atr_pct", risk_rules["high_atr_pct"]),
        ("realized_volatility", risk_rules["high_realized_volatility"]),
        ("intraday_range_pct", risk_rules["high_intraday_range_pct"]),
        ("recent_max_drawdown_pct", risk_rules["high_recent_drawdown_pct"]))
    for name, threshold in volatility_fields:
        value = volatility.get(name)
        if value is not None:
            known_volatility += 1
            if value >= threshold: volatility_penalty += risk_rules["volatility_penalty_each"]
    volatility_penalty += (len(volatility_fields) - known_volatility) * risk_rules["missing_volatility_penalty_each"]
    risk["volatility"] = {"penalty": volatility_penalty, "values": volatility}
    chase_score, chase_level, advance = chase_risk(inputs["current_price"], inputs.get("recovery_signal_price"), config)
    chase_penalty = round(config["chase"]["maximum_penalty"] * chase_score / 100)
    risk["chase"] = {"penalty": chase_penalty, "score": chase_score, "level": chase_level, "advance": advance}
    penalty = min(risk_rules["maximum_penalty"], sum(item["penalty"] for item in risk.values()))
    final = 0 if hard_reject else max(0, raw - penalty)
    desired = "REJECT" if hard_reject else base_status(final, config)
    matrix_limited = False
    if not hard_reject:
        cap = config["matrix_caps"].get(inputs["recovery_stage"], "WAIT")
        if STATUS_ORDER[desired] > STATUS_ORDER[cap]: desired = cap; matrix_limited = True
        if previous is not None and STATUS_ORDER.get(previous.buy_status, 0) > STATUS_ORDER[cap]:
            matrix_limited = True
        if inputs["recovery_stage"] in ("PANIC", "STABILIZING") and STATUS_ORDER[desired] < STATUS_ORDER["WATCH"]:
            desired = "WATCH"
        if confidence == "LOW" and STATUS_ORDER[desired] > STATUS_ORDER["WATCH"]: desired = "WATCH"
        if chase_level == "HIGH" and STATUS_ORDER[desired] > STATUS_ORDER["WATCH"]: desired = "WATCH"
        if inputs["recovery_stage"] == "FAILED_RECOVERY": desired = "WAIT"
    cooldown_until = None
    if inputs["recovery_stage"] == "FAILED_RECOVERY" and evaluation_time is not None:
        cooldown_until = evaluation_time + timedelta(minutes=config["hysteresis"]["failed_recovery_cooldown_minutes"])
    safety_limited = hard_reject or matrix_limited or confidence == "LOW" or chase_level == "HIGH" or inputs["recovery_stage"] == "FAILED_RECOVERY"
    status = desired if safety_limited else apply_hysteresis(desired, final, previous, evaluation_time, config)
    if previous is not None and previous.cooldown_until is not None and evaluation_time is not None and evaluation_time < previous.cooldown_until and STATUS_ORDER.get(status, 0) > STATUS_ORDER["WAIT"]:
        status = "WAIT"; cooldown_until = previous.cooldown_until
        risk["cooldown"] = {"penalty": 0, "until": previous.cooldown_until.isoformat()}
    action = {
        "REJECT": "REJECT", "WAIT": "WAIT", "WATCH": "WATCH_CLOSELY",
        "EARLY_ENTRY": "EARLY_ENTRY_CANDIDATE", "CONFIRMED_ENTRY": "CONFIRMED_ENTRY_CANDIDATE",
        "STRONG_ENTRY": "STRONG_ENTRY_CANDIDATE",
    }[status]
    entry_attractiveness = {"HIGH": "LOW", "MEDIUM": "MEDIUM", "LOW": "HIGH", "UNKNOWN": "UNKNOWN"}[chase_level]
    position_confidence = "LOW" if confidence == "LOW" or volatility_penalty >= 8 or chase_level == "HIGH" else ("MEDIUM" if confidence == "MEDIUM" or volatility_penalty >= 4 or chase_level == "MEDIUM" else "HIGH")
    return {"raw_buy_score": raw, "risk_penalty": penalty, "final_buy_score": final,
            "buy_grade": grade(final, config), "buy_status": status, "recommended_action": action,
            "chase_risk_score": chase_score, "chase_risk_level": chase_level,
            "entry_attractiveness": entry_attractiveness,
            "recommended_position_confidence": position_confidence,
            "cooldown_until": cooldown_until, "components": {"inputs": source_scores, "risk": risk}}


def apply_hysteresis(desired, score, previous, evaluation_time, config):
    if previous is None or desired in ("REJECT", "WAIT") and getattr(previous, "buy_status", None) == "REJECT":
        return desired
    current = previous.buy_status
    if current == desired:
        return desired
    if desired == "REJECT":
        return desired
    elapsed = None if evaluation_time is None else (evaluation_time - previous.evaluation_time).total_seconds() / 60
    if elapsed is not None and elapsed < config["hysteresis"]["minimum_state_duration_minutes"]:
        return current
    if STATUS_ORDER.get(desired, 0) < STATUS_ORDER.get(current, 0):
        threshold_key = {"STRONG_ENTRY": "strong_entry", "CONFIRMED_ENTRY": "confirmed_entry", "EARLY_ENTRY": "early_entry", "WATCH": "watch"}.get(current)
        if threshold_key and score >= config["status_thresholds"][threshold_key] - config["hysteresis"]["downgrade_buffer"]:
            return current
    return desired


def combined_confidence(qmr_confidence, recovery_confidence):
    return min((qmr_confidence, recovery_confidence), key=lambda value: CONFIDENCE_ORDER.get(value, 0))
