from app.qmr_exit.scoring import evaluate_exit


def exit_engine_path(bars, entry, config):
    """Daily-bar research path. Each decision sees only the prefix through that bar."""
    if not bars:
        return {"exit_reason": "NO_DATA", "realized_return": None}
    highest, remaining, realized, reductions = float(entry), 1.0, 0.0, []
    final_state, exit_index, exit_price = "HOLD", len(bars), float(bars[-1].close)
    for index, bar in enumerate(bars, 1):
        highest = max(highest, float(bar.high))
        prefix = bars[:index]
        previous_state = final_state
        result = evaluate_exit(entry, highest, float(bar.close), {"1d": prefix, "60m": [], "30m": []},
            {}, [], {}, {"data_available": False, "money_flow_score": None, "regime": "NEUTRAL"},
            config, previous_state)
        final_state = result["state"]
        if final_state == "REDUCE" and previous_state != "REDUCE" and remaining > .01:
            ratio = min(remaining, remaining * float(result["reduce_ratio"] or 0))
            realized += ratio * (float(bar.close) / entry - 1)
            remaining -= ratio
            reductions.append({"bar": index, "ratio": ratio, "price": float(bar.close),
                               "risk": result["exit_risk_score"]})
        if final_state == "EXIT":
            realized += remaining * (float(bar.close) / entry - 1)
            remaining, exit_index, exit_price = 0.0, index, float(bar.close)
            break
    if remaining:
        realized += remaining * (exit_price / entry - 1)
    peak_return = (highest / entry - 1) * 100
    realized_pct = realized * 100
    return {"exit_date_index": exit_index, "exit_price": exit_price,
            "exit_reason": final_state if final_state == "EXIT" else "END_OF_WINDOW",
            "realized_return": realized_pct, "peak_price": highest, "peak_return": peak_return,
            "profit_giveback": max(0, peak_return - realized_pct),
            "captured_mfe_ratio": realized_pct / peak_return if peak_return > 0 else None,
            "holding_days": exit_index, "reductions": reductions}


def comparison_paths(bars, entry, config):
    def fixed(days):
        sample = bars[:days]
        return (float(sample[-1].close) / entry - 1) * 100 if len(sample) == days else None
    target = None
    for index, bar in enumerate(bars, 1):
        if float(bar.high) >= entry * 1.10:
            target = {"return": 10.0, "holding_days": index}; break
    if target is None and bars:
        target = {"return": (float(bars[-1].close) / entry - 1) * 100, "holding_days": len(bars)}
    traditional = None
    for index, bar in enumerate(bars, 1):
        hit_target, hit_stop = float(bar.high) >= entry * 1.10, float(bar.low) <= entry * .93
        if hit_target or hit_stop:
            traditional = {"return": -7.0 if hit_stop else 10.0, "holding_days": index,
                           "reason": "STOP" if hit_stop else "TARGET"}; break
    if traditional is None and bars:
        traditional = {"return": (float(bars[-1].close) / entry - 1) * 100,
                       "holding_days": len(bars), "reason": "TIME"}
    return {"fixed_5d": fixed(5), "fixed_10d": fixed(10), "target_10pct": target,
            "traditional_target_stop": traditional, "qmr_exit_engine": exit_engine_path(bars, entry, config)}
