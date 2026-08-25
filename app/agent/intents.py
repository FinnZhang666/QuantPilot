import re
from dataclasses import dataclass
from enum import Enum


class AgentIntent(str, Enum):
    SYMBOL_ANALYSIS = "SYMBOL_ANALYSIS"
    MARKET_CONTEXT = "MARKET_CONTEXT"
    SECTOR_CONTEXT = "SECTOR_CONTEXT"
    QMR_STATUS = "QMR_STATUS"
    MONEY_FLOW = "MONEY_FLOW"
    POSITION = "POSITION"
    EXIT_RISK = "EXIT_RISK"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    USER_TRADE_RECORD = "USER_TRADE_RECORD"
    EXPLANATION = "EXPLANATION"


@dataclass(frozen=True)
class ParsedIntent:
    intent: AgentIntent
    tool_name: str
    symbol: str = None
    arguments: dict = None


_SYMBOL = re.compile(r"(?<![A-Z0-9])\$?(?:US\.)?([A-Z][A-Z0-9.-]{0,15})(?![A-Z0-9])")


def symbol_from_text(text):
    ignored = {"AI", "QMR", "BUY", "SELL", "ET", "APPROVE"}
    for value in _SYMBOL.findall(str(text or "").upper()):
        if value not in ignored:
            return value
    return None


def parse_intent(text, reply_signal_id=None):
    raw = str(text or "").strip()
    lower = raw.lower()
    symbol = symbol_from_text(raw)
    if reply_signal_id and any(key in raw for key in (
            "为什么没买", "为什么没有买", "没成交", "没有成交", "订单", "order")):
        return ParsedIntent(AgentIntent.EXPLANATION, "get_paper_orders", symbol,
                            {"signal_id": reply_signal_id})
    bought = re.search(r"(?:我买了|record(?:ed)? buy)\s*\$?(?:US\.)?([A-Z][A-Z0-9.-]*)\s+(\d+(?:\.\d+)?)\s*(?:股|shares?)?\s*(?:@|at|，|,|\s)\s*\$?(\d+(?:\.\d+)?)", raw, re.I)
    if bought:
        return ParsedIntent(AgentIntent.USER_TRADE_RECORD, "record_user_trade", bought.group(1).upper(),
                            {"quantity": bought.group(2), "average_cost": bought.group(3)})
    if any(key in raw for key in ("帮我买", "替我买", "下单", "立即买入")) or "place order" in lower:
        return ParsedIntent(AgentIntent.EXPLANATION, "analyze_symbol", symbol,
                            {"execution_requested": True})
    if re.search(r"#?QMR-\d{8}-\d{3}", raw, re.I):
        signal_id = re.search(r"#?(QMR-\d{8}-\d{3})", raw, re.I).group(1).upper()
        return ParsedIntent(AgentIntent.SIGNAL, "get_recent_signals", symbol,
                            {"signal_id": signal_id})
    rules = (
        (("为什么没买", "订单", "order"), AgentIntent.ORDER, "get_paper_orders"),
        (("退出风险", "卖出风险", "exit risk"), AgentIntent.EXIT_RISK, "get_exit_risk"),
        (("资金流", "资金结构", "money flow"), AgentIntent.MONEY_FLOW, "get_money_flow"),
        (("持仓", "仓位", "position"), AgentIntent.POSITION, "get_position"),
        (("qmr", "优质错杀"), AgentIntent.QMR_STATUS, "get_qmr_analysis"),
        (("行业", "板块", "sector"), AgentIntent.SECTOR_CONTEXT, "get_sector_context"),
        (("大盘", "市场状态", "market context"), AgentIntent.MARKET_CONTEXT, "get_market_context"),
        (("信号", "signal"), AgentIntent.SIGNAL, "get_recent_signals"),
        (("分析", "怎么看", "怎么样", "analyze"), AgentIntent.SYMBOL_ANALYSIS, "analyze_symbol"),
    )
    for keys, intent, tool in rules:
        if any(key.lower() in lower for key in keys):
            return ParsedIntent(intent, tool, symbol, {})
    return None
