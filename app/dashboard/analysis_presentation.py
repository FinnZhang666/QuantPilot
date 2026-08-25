"""Deterministic, bilingual presentation rules for persisted analysis facts.

This module translates engine output for people.  It deliberately performs no
strategy evaluation and never manufactures missing prices or recommendations.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


LABELS = {
    "zh-CN": {
        "VERY_STRONG": "很强", "STRONG": "强", "NEUTRAL": "中性",
        "WEAK": "偏弱", "VERY_WEAK": "很弱", "LOW_VALUATION": "偏低",
        "FAIR_VALUATION": "合理", "HIGH_VALUATION": "偏高",
        "UNAVAILABLE": "数据不足", "FRESH": "最新", "DELAYED": "延迟",
        "STALE": "已过期", "VALUE_TRAP_LOW": "价值陷阱风险较低",
        "VALUE_TRAP_PRESENT": "存在价值陷阱风险", "LEVERAGED_ETF_ANALYSIS": "杠杆ETF交易载体分析",
        "QMR_ANALYSIS": "QMR 优质错杀修复", "STOCK": "股票", "ETF": "ETF",
        "LEVERAGED_ETF": "杠杆ETF", "POSITIVE": "支持因素", "CAUTION": "风险因素",
    },
    "en-US": {
        "VERY_STRONG": "Very strong", "STRONG": "Strong", "NEUTRAL": "Neutral",
        "WEAK": "Weak", "VERY_WEAK": "Very weak", "LOW_VALUATION": "Below peers",
        "FAIR_VALUATION": "Fair", "HIGH_VALUATION": "Above peers",
        "UNAVAILABLE": "Unavailable", "FRESH": "Fresh", "DELAYED": "Delayed",
        "STALE": "Stale", "VALUE_TRAP_LOW": "Lower value-trap risk",
        "VALUE_TRAP_PRESENT": "Value-trap risk present", "LEVERAGED_ETF_ANALYSIS": "Leveraged ETF vehicle analysis",
        "QMR_ANALYSIS": "QMR Quality Mispricing Recovery", "STOCK": "Stock", "ETF": "ETF",
        "LEVERAGED_ETF": "Leveraged ETF", "POSITIVE": "Supporting factors", "CAUTION": "Risk factors",
    },
}

INFO = {
    "quality": {
        "zh-CN": "公司质量来自已保存的盈利、增长、资本效率、现金流与资产负债表评分。",
        "en-US": "Quality uses persisted profitability, growth, capital efficiency, cash-flow and balance-sheet facts.",
    },
    "valuation": {
        "zh-CN": "估值结合已有同业、行业、市场或公司历史数据；便宜本身不等于买入。",
        "en-US": "Valuation uses available peer, industry, market or historical comparisons; cheap alone is not a buy signal.",
    },
    "global": {
        "zh-CN": "Global 反映已保存的全球市场风险环境，不单独产生买卖信号。",
        "en-US": "Global reflects the persisted market risk backdrop and does not create a trade signal alone.",
    },
    "sector": {
        "zh-CN": "Sector 反映行业相对强弱、广度与轮动状态。",
        "en-US": "Sector reflects persisted relative strength, breadth and rotation state.",
    },
    "buy_score": {
        "zh-CN": "买入评分由 QMR 现有评分引擎生成；解释层不会重新计算。",
        "en-US": "Buy Score is produced by the existing QMR engine; the presentation layer does not recalculate it.",
    },
    "exit_risk": {
        "zh-CN": "退出风险来自现有 Exit Engine，仅用于持仓风险管理。",
        "en-US": "Exit Risk comes from the existing Exit Engine for position risk management.",
    },
}

STATUS_LABELS = {
    "zh-CN": {"WATCH": "观察", "EARLY_ENTRY": "早期介入", "CONFIRMED_ENTRY": "确认介入",
        "STRONG_ENTRY": "强确认", "HOLD": "持有", "PROTECT": "保护利润", "REDUCE": "减仓",
        "EXIT": "退出", "NO_DATA": "数据不足", "WAIT_FOR_CONFIRMATION": "等待确认",
        "SMALL_PROBE": "小仓试探", "SMALL_POSITION": "小仓介入", "CONSIDER_ENTRY": "考虑介入",
        "PROTECT_PROFIT": "保护利润", "REDUCE_POSITION": "考虑减仓", "EXIT_POSITION": "考虑退出",
        "DATA_INSUFFICIENT": "数据不足", "QUALITY_MISPRICING_CANDIDATE": "优质错杀候选"},
    "en-US": {"WATCH": "Watch", "EARLY_ENTRY": "Early entry", "CONFIRMED_ENTRY": "Confirmed entry",
        "STRONG_ENTRY": "Strong entry", "HOLD": "Hold", "PROTECT": "Protect profits", "REDUCE": "Reduce",
        "EXIT": "Exit", "NO_DATA": "Insufficient data", "WAIT_FOR_CONFIRMATION": "Wait for confirmation",
        "SMALL_PROBE": "Small probe", "SMALL_POSITION": "Small position", "CONSIDER_ENTRY": "Consider entry",
        "PROTECT_PROFIT": "Protect profits", "REDUCE_POSITION": "Consider reducing", "EXIT_POSITION": "Consider exit",
        "DATA_INSUFFICIENT": "Insufficient data", "QUALITY_MISPRICING_CANDIDATE": "Quality mispricing candidate"},
}


def label(code, language="zh-CN"):
    return LABELS.get(language, LABELS["en-US"]).get(code, str(code or "—").replace("_", " ").title())


def status_label(code, language="zh-CN"):
    return STATUS_LABELS.get(language, STATUS_LABELS["en-US"]).get(code, label(code, language))


def score_state(value):
    if value is None:
        return "UNAVAILABLE"
    value = float(value)
    if value >= 80: return "VERY_STRONG"
    if value >= 65: return "STRONG"
    if value >= 45: return "NEUTRAL"
    if value >= 30: return "WEAK"
    return "VERY_WEAK"


def valuation_view(qmr):
    mispricing = ((qmr or {}).get("score_components") or {}).get("mispricing") or {}
    peer = mispricing.get("peer") or {}
    score = peer.get("score")
    available = bool(peer.get("available", score is not None)) and score is not None
    if not available:
        state = "UNAVAILABLE"
    elif float(score) >= 65:
        state = "LOW_VALUATION"
    elif float(score) >= 40:
        state = "FAIR_VALUATION"
    else:
        state = "HIGH_VALUATION"
    trap = mispricing.get("value_trap") or {}
    flags = list(trap.get("flags") or trap.get("reasons") or [])
    return {
        "available": available, "score": score if available else None, "state": state,
        "peer_method": peer.get("peer_method") or peer.get("method"),
        "peer_count": peer.get("peer_count") or peer.get("sample_count"),
        "confidence": peer.get("peer_confidence") or peer.get("confidence"), "factor_coverage": peer.get("factor_coverage"),
        "value_trap_state": "VALUE_TRAP_PRESENT" if flags or float(trap.get("deduction") or 0) > 0 else "VALUE_TRAP_LOW",
        "value_trap_flags": flags,
    }


def freshness(timestamp, now=None):
    if timestamp is None:
        return {"status": "UNAVAILABLE", "age_seconds": None}
    if isinstance(timestamp, str):
        try: timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError: return {"status": "UNAVAILABLE", "age_seconds": None}
    if timestamp.tzinfo is None: timestamp = timestamp.replace(tzinfo=timezone.utc)
    age = max(0, int(((now or datetime.now(timezone.utc)) - timestamp.astimezone(timezone.utc)).total_seconds()))
    return {"status": "FRESH" if age <= 3600 else "DELAYED" if age <= 86400 else "STALE", "age_seconds": age}


def risk_reward(entry, invalidation, targets):
    """Only expose R/R when a persisted plan supplies all required prices."""
    try:
        entry_value, stop_value = Decimal(str(entry)), Decimal(str(invalidation))
        target_values = [Decimal(str(value)) for value in (targets or []) if value is not None]
    except (InvalidOperation, TypeError, ValueError):
        return {"status": "UNAVAILABLE", "ratio": None, "reason": "MISSING_RELIABLE_PLAN_LEVELS"}
    risk = entry_value - stop_value
    if risk <= 0 or not target_values:
        return {"status": "UNAVAILABLE", "ratio": None, "reason": "MISSING_RELIABLE_PLAN_LEVELS"}
    reward = target_values[0] - entry_value
    if reward <= 0:
        return {"status": "UNAVAILABLE", "ratio": None, "reason": "INVALID_PLAN_LEVELS"}
    return {"status": "AVAILABLE", "ratio": round(float(reward / risk), 2),
            "entry": str(entry_value), "invalidation": str(stop_value), "target": str(target_values[0])}


def localized_view(payload, language):
    """Return labels without replacing the stable machine-readable states."""
    valuation = payload.get("valuation") or {}
    return {
        "language": language,
        "analysis_model": label(payload.get("analysis_model"), language),
        "asset_type": label((payload.get("instrument") or {}).get("asset_type"), language),
        "quality": label(score_state(payload.get("quality_score")), language),
        "valuation": label(valuation.get("state"), language),
        "value_trap": label(valuation.get("value_trap_state"), language),
        "global": label(score_state(((payload.get("market_context") or {}).get("global") or {}).get("global_score")), language),
        "sector": label(score_state(((payload.get("market_context") or {}).get("sector") or {}).get("sector_score")), language),
        "freshness": label((payload.get("freshness") or {}).get("status"), language),
        "status": status_label(payload.get("status"), language),
        "advice": status_label(payload.get("advice"), language),
        "qmr": status_label(payload.get("qmr_summary"), language),
        "info": {key: value[language] for key, value in INFO.items()},
    }
