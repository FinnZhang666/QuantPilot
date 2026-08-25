"""Pure Gate + Score logic.  It never creates orders or mutates strategy data."""


def entry_gate(buy_status, buy_score, quality_pass, recovery_pass, data_complete,
               executable, duplicate_free, global_context, sector_context, config):
    reasons = []
    if not quality_pass: reasons.append("QUALITY_GATE_FAILED")
    if not recovery_pass: reasons.append("RECOVERY_GATE_FAILED")
    if not data_complete: reasons.append("DATA_COMPLETENESS_FAILED")
    if not executable: reasons.append("SESSION_NOT_EXECUTABLE")
    if not duplicate_free: reasons.append("DUPLICATE_EXECUTION")
    global_score = global_context.get("global_score") if global_context else None
    sector_score_value = sector_context.get("sector_score") if sector_context else None
    if global_score is None: reasons.append("GLOBAL_CONTEXT_UNAVAILABLE")
    elif global_score < config["global_block_below"]: reasons.append("GLOBAL_RISK_OFF")
    if sector_score_value is None: reasons.append("SECTOR_CONTEXT_UNAVAILABLE")
    elif sector_score_value < config["sector_block_below"]: reasons.append("SECTOR_VERY_WEAK")
    hard_blocks = {"QUALITY_GATE_FAILED", "RECOVERY_GATE_FAILED", "DATA_COMPLETENESS_FAILED",
                   "SESSION_NOT_EXECUTABLE", "DUPLICATE_EXECUTION", "GLOBAL_RISK_OFF",
                   "SECTOR_VERY_WEAK", "GLOBAL_CONTEXT_UNAVAILABLE",
                   "SECTOR_CONTEXT_UNAVAILABLE"}
    if hard_blocks.intersection(reasons):
        decision = "WAIT"
    elif global_score is None or sector_score_value is None or global_score < config["global_probe_below"] or sector_score_value < config["sector_probe_below"]:
        decision = "PROBE"
    else:
        decision = buy_status
    global_state = (global_context or {}).get("global_state", "DATA_UNAVAILABLE")
    sector_state = (sector_context or {}).get("sector_state", "DATA_UNAVAILABLE")
    multiplier = (float(config["multipliers"]["global"].get(global_state, 0)) *
                  float(config["multipliers"]["sector"].get(sector_state, 0)))
    if decision == "WAIT": multiplier = 0
    return {"decision": decision, "position_multiplier": round(multiplier, 4),
            "reasons": reasons, "stock_score": buy_score,
            "global_score": global_score, "global_state": global_state,
            "sector_score": sector_score_value, "sector_state": sector_state}


def exit_context_adjustment(global_context, sector_context, previous_global=None,
                            previous_sector=None):
    global_score = (global_context or {}).get("global_score")
    sector_score = (sector_context or {}).get("sector_score")
    risk, reasons = 0, []
    if global_score is not None and global_score < 50:
        risk += min(10, (50 - global_score) * .35); reasons.append("GLOBAL_CONTEXT_DETERIORATING")
    if sector_score is not None and sector_score < 50:
        risk += min(10, (50 - sector_score) * .35); reasons.append("SECTOR_CONTEXT_DETERIORATING")
    if previous_global is not None and global_score is not None and previous_global - global_score >= 15:
        risk += 5; reasons.append("GLOBAL_CONTEXT_FAST_DROP")
    if previous_sector is not None and sector_score is not None and previous_sector - sector_score >= 15:
        risk += 5; reasons.append("SECTOR_CONTEXT_FAST_DROP")
    return {"risk_addition": min(20, round(risk)), "reasons": reasons}
