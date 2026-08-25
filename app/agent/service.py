import json
from datetime import date, datetime
from decimal import Decimal

from app.agent.intents import parse_intent
from app.core.errors import ControlledServiceError
from app.telegram_runtime.renderer import TelegramMessage
from app.agent.tools import AgentToolService


class AgentService:
    def __init__(self, db, settings):
        self.tools = AgentToolService(db, settings)

    def route(self, text, user, reply_signal_id=None):
        parsed = parse_intent(text, reply_signal_id)
        if parsed is None:
            return None
        arguments = dict(parsed.arguments or {})
        if parsed.tool_name == "record_user_trade":
            arguments["user_id"] = user.telegram_user_id
        try:
            result = self.tools.call(
                parsed.tool_name, chat_id=user.chat_id, intent=parsed.intent.value,
                symbol=parsed.symbol, **arguments)
            return TelegramMessage(self._format(parsed.intent.value, result, user.language))
        except ControlledServiceError as exc:
            return TelegramMessage(exc.error.user_message(user.language))

    @classmethod
    def _format(cls, intent, result, language):
        zh = language == "zh-CN"
        if result.get("execution_blocked"):
            return result["message"] if zh else "Trade Companion does not place real orders. I can analyze or record your own trade."
        symbol = result.get("symbol") or (result.get("signal") or {}).get("symbol") or ""
        if intent == "SYMBOL_ANALYSIS" or ("status" in result and "advice" in result):
            presentation = (result.get("presentation") or {}).get(language) or {}
            return cls._lines(
                ("📈 主动分析" if zh else "📈 Analysis"), symbol,
                ("分析模型" if zh else "Model") + ": " + str(presentation.get("analysis_model", "—")),
                ("状态" if zh else "Status") + ": " + str(presentation.get("status", result.get("status", "—"))),
                ("公司质量" if zh else "Quality") + ": " + str(presentation.get("quality", "—")),
                ("估值" if zh else "Valuation") + ": " + str(presentation.get("valuation", "—")),
                "Global: " + str(presentation.get("global", "—")),
                "Sector: " + str(presentation.get("sector", "—")),
                ("当前价" if zh else "Price") + ": " + cls._value(result.get("current_price")),
                ("买入评分" if zh else "Buy score") + ": " + cls._value(result.get("buy_score")),
                ("退出风险" if zh else "Exit risk") + ": " + cls._value(result.get("exit_risk")),
                ("最终建议" if zh else "Final action") + ": " + str(presentation.get("advice", result.get("advice", "—"))),
                ("数据缺失" if zh else "Missing") + ": " + ", ".join(result.get("missing_sections") or [])
            )
        if intent == "MONEY_FLOW":
            flow = result.get("money_flow") or {}
            return cls._lines("💰 " + ("资金结构" if zh else "Money flow"), symbol,
                              ("状态" if zh else "Regime") + ": " + str(flow.get("regime", "数据不足")),
                              ("评分" if zh else "Score") + ": " + cls._value(flow.get("score")))
        if intent == "POSITION":
            rows = result.get("positions") or []
            return cls._lines("💼 " + ("模拟持仓" if zh else "Paper positions"),
                              *["%s | %s | %s" % (r["symbol"], r["status"], cls._value(r["quantity"])) for r in rows[:10]]) if rows else ("暂无模拟持仓" if zh else "No paper positions")
        if intent == "EXIT_RISK":
            value = result.get("exit") or {}
            return cls._lines("🛡 " + ("退出风险" if zh else "Exit risk"), symbol,
                              "State: " + str(value.get("state", "暂无")),
                              "Risk: " + cls._value(value.get("exit_risk_score")),
                              "Reasons: " + ", ".join(value.get("reasons_json") or []))
        if intent == "ORDER" or intent == "EXPLANATION":
            return cls._lines("📋 " + ("模拟订单状态" if zh else "Paper order status"), symbol,
                              ("原因" if zh else "Reason") + ": " + str(result.get("reason", "NO_PAPER_ORDER")),
                              ("系统不会自动转入真实账户。" if zh else "The system never falls back to a real account."))
        if intent == "USER_TRADE_RECORD":
            return cls._lines("✅ " + ("已记录你的交易" if zh else "Trade recorded"), symbol,
                              ("仅为内部记录，不是券商成交。" if zh else "This is an internal record, not a broker fill."))
        if intent == "SIGNAL":
            rows = result.get("signals") or ([result["signal"]] if result.get("signal") else [])
            return cls._lines("🔔 QMR Signals", *["%s | %s | %s" %
                (r["signal_id"], r["symbol"], r["status"]) for r in rows[:10]])
        if intent in {"MARKET_CONTEXT", "SECTOR_CONTEXT"}:
            return cls._lines("🌍 " + ("市场上下文" if zh else "Market context"), symbol,
                              cls._json(result))
        return cls._json(result)

    @staticmethod
    def _lines(*values):
        return "\n".join(str(value) for value in values if value not in (None, ""))[:4000]

    @staticmethod
    def _value(value):
        return "暂无" if value is None else str(value)

    @staticmethod
    def _json(value):
        def default(item):
            if isinstance(item, (datetime, date)): return item.isoformat()
            if isinstance(item, Decimal): return str(item)
            return str(item)
        return json.dumps(value, ensure_ascii=False, default=default, indent=2)[:3400]
