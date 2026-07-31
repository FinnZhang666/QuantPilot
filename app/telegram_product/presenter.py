import re
from decimal import Decimal, InvalidOperation

from app.telegram_product.deep_links import deep_link
from app.telegram_product.i18n import translations
from app.telegram_product.models import TelegramActionButton, TelegramSymbolOverview


MAX_MESSAGE_LENGTH = 4000
SCHEMA_VERSION = "telegram-symbol-overview-v1"


def _safe(value):
    text = "" if value is None else str(value)
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)


def _number(value, missing):
    if value is None or value == "":
        return missing
    try:
        return _safe(format(Decimal(str(value)).normalize(), "f"))
    except InvalidOperation:
        return _safe(value)


class TelegramPresenter:
    """Transforms service DTOs only; never reads storage, network, or Telegram API."""

    def symbol_overview(self, overview, language="zh-CN"):
        t = translations(language)
        snapshot = overview.snapshot
        plan, holding, review, analysis = (
            overview.trade_plan, overview.holding, overview.review, overview.ai_analysis,
        )
        sections = [
            {"title": t["snapshot"], "value": "%s: %s\n%s: %s" % (
                t["price"], _number(snapshot.latest_price, t["none"]),
                t["candidate"], _safe(snapshot.candidate_signal),
            )},
            {"title": t["holding"], "value": (
                "%s · %s @ %s" % (_safe(holding["status"]), _number(holding["quantity"], t["none"]),
                                    _number(holding["average_cost"], t["none"]))
                if holding else t["none"]
            )},
            {"title": t["plan"], "value": (
                "%s · %s · %s" % (_safe(plan["lifecycle_stage"]), _safe(plan["direction"]),
                                    _safe(plan["timeframe"])) if plan else t["none"]
            )},
            {"title": t["review"], "value": _safe(review["result"]) if review else t["none"]},
            {"title": t["ai"], "value": _safe(analysis["summary"]) if analysis else t["none"]},
        ]
        buttons = self._buttons(overview, t)
        return TelegramSymbolOverview(
            SCHEMA_VERSION, language, overview.symbol, overview.market,
            t["title"].format(symbol=_safe(overview.symbol)), sections, buttons,
        )

    def format(self, view_model):
        t = translations(view_model.language)
        parts = [view_model.title]
        for section in view_model.sections:
            parts.extend(("", section["title"], section["value"]))
        parts.extend(("", t["disclaimer"]))
        text = "\n".join(parts)
        if len(text) <= MAX_MESSAGE_LENGTH:
            return text
        ending = "\n\n" + t["disclaimer"]
        return text[:MAX_MESSAGE_LENGTH - len(ending) - 1] + "…" + ending

    def preview(self, overview, language="zh-CN"):
        view_model = self.symbol_overview(overview, language)
        return {"message": self.format(view_model), "view_model": view_model.model_dump(),
                "buttons": [button.__dict__ for button in view_model.buttons],
                "preview": True, "sent": False}

    @staticmethod
    def _buttons(overview, t):
        related = overview.related_objects
        definitions = [
            ("snapshot", "view_snapshot", "symbol", overview.symbol),
            ("trade_plan", "view_plan", "trade_plan",
             overview.trade_plan["plan_id"] if overview.trade_plan else overview.symbol),
            ("holding", "view_holding", "holding",
             overview.holding["id"] if overview.holding else overview.symbol),
            ("review", "view_review", "review",
             overview.review["id"] if overview.review else overview.symbol),
            ("ai", "view_ai", "ai",
             overview.ai_analysis["id"] if overview.ai_analysis else overview.symbol),
        ]
        result = []
        for key, label, kind, target in definitions:
            result.append(TelegramActionButton(
                t[label], "view_%s" % key, str(target), deep_link(kind, target),
                bool(related[key]["available"]),
            ))
        if overview.snapshot.portfolio_id:
            result.append(TelegramActionButton(
                t["portfolio"], "view_portfolio", str(overview.snapshot.portfolio_id),
                deep_link("portfolio", overview.snapshot.portfolio_id), True,
            ))
        return result
