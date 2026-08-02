import html
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.telegram_product.bot_profiles import TelegramBotProfile


TELEGRAM_TEXT_LIMIT = 4096
SUPPORTED_LANGUAGES = {"zh-CN", "en-US"}

WELCOME_TEXT = {
    "zh-CN": (
        "<b>Trade Companion</b>\n\n"
        "陪你走过每一次交易，而不是只推送一个买卖点。\n\n"
        "我们持续分析市场，\n持续记录策略表现，\n持续复盘每一笔模拟交易，\n"
        "帮助你建立自己的交易体系。\n\n"
        "Trade Companion 不替你做决定，\n只帮助你做出更好的决定。\n\n"
        "投资是一场长期旅程。\n\n我会一直陪伴你。"
    ),
    "en-US": (
        "<b>Trade Companion</b>\n\n"
        "With you through every trade, not just another buy or sell signal.\n\n"
        "We continuously analyze the market,\ntrack strategy performance,\n"
        "review every paper trade,\nand help you build your own trading system.\n\n"
        "Trade Companion does not make decisions for you.\n"
        "It helps you make better decisions.\n\n"
        "Investing is a long-term journey.\n\nI will be with you along the way."
    ),
}

DISCLAIMER = {
    "zh-CN": (
        "免责声明：本报告仅基于 Trade Companion 系统数据进行客观分析，"
        "不构成投资建议。投资有风险，请独立判断并自行承担决策责任。"
    ),
    "en-US": (
        "Disclaimer: This report is an objective analysis based only on Trade Companion "
        "system data. It is not investment advice. Investing involves risk; make independent "
        "decisions and accept responsibility for them."
    ),
}

MAIN_MENU = {
    "zh-CN": (
        ("📈 AI分析", "analyze"), ("💼 我的投资", "portfolio"),
        ("🌍 市场快照", "market"), ("💡 更多", "more"),
    ),
    "en-US": (
        ("📈 AI Analysis", "analyze"), ("💼 My Investments", "portfolio"),
        ("🌍 Market Snapshot", "market"), ("💡 More", "more"),
    ),
}


@dataclass(frozen=True)
class TelegramMessage:
    text: str
    reply_markup: Optional[Dict[str, object]] = None
    parse_mode: str = "HTML"

    def as_payload(self, chat_id: Optional[str] = None) -> Dict[str, object]:
        payload: Dict[str, object] = {"text": self.text, "parse_mode": self.parse_mode}
        if chat_id is not None:
            payload["chat_id"] = chat_id
        if self.reply_markup:
            payload["reply_markup"] = self.reply_markup
        return payload


def normalize_language(language: str) -> str:
    return language if language in SUPPORTED_LANGUAGES else "zh-CN"


def callback_keyboard(rows: List[List[tuple]]) -> Dict[str, object]:
    return {"inline_keyboard": [[
        {"text": label, "callback_data": "tc:" + action} for label, action in row
    ] for row in rows]}


def main_menu(language: str) -> Dict[str, object]:
    items = MAIN_MENU[normalize_language(language)]
    return callback_keyboard([
        [items[0], items[1]],
        [items[2], items[3]],
    ])


def welcome(profile: TelegramBotProfile, language: str) -> TelegramMessage:
    del profile
    selected = normalize_language(language)
    return TelegramMessage(WELCOME_TEXT[selected], main_menu(selected))


def more(language: str) -> TelegramMessage:
    zh = normalize_language(language) == "zh-CN"
    return TelegramMessage(
        "请选择功能：" if zh else "Choose an option:",
        callback_keyboard([
            [("使用帮助" if zh else "Help", "help"),
             ("提交建议" if zh else "Feedback", "feedback")],
            [("更新日志" if zh else "Updates", "updates"),
             ("切换语言" if zh else "Change Language", "language")],
            [("关于我们" if zh else "About", "about")],
            [("我的关注" if zh else "Watchlist", "watchlist"),
             ("当前持仓" if zh else "Holdings", "holding")],
            [("历史记录" if zh else "History", "history"),
             ("交易复盘" if zh else "Reviews", "review")],
        ]),
    )


def help_message(language: str) -> TelegramMessage:
    zh = normalize_language(language) == "zh-CN"
    text = (
        "<b>使用帮助</b>\n\n"
        "• 点击“AI分析”后输入股票代码，例如 PLTR。\n"
        "• “我的投资”查看投资组合与持仓。\n"
        "• “市场快照”查看系统市场数据。\n"
        "• “更多”可提交建议、查看更新或切换语言。"
        if zh else
        "<b>Help</b>\n\n"
        "• Choose AI Analysis, then enter a symbol such as PLTR.\n"
        "• My Investments shows portfolios and holdings.\n"
        "• Market Snapshot shows system market data.\n"
        "• More provides feedback, updates, and language settings."
    )
    return TelegramMessage(text, main_menu(language))


def updates_message(language: str) -> TelegramMessage:
    zh = normalize_language(language) == "zh-CN"
    text = (
        "<b>更新日志</b>\n\n• 单 Bot 多语言流程\n• AI 输出采用安全 HTML\n• 管理员反馈通知"
        if zh else
        "<b>Updates</b>\n\n• Single-Bot multilingual flow\n• Safe HTML AI output\n"
        "• Administrator feedback notifications"
    )
    return TelegramMessage(text, main_menu(language))


def about_message(language: str) -> TelegramMessage:
    zh = normalize_language(language) == "zh-CN"
    text = (
        "<b>关于 Trade Companion</b>\n\n"
        "Trade Companion 陪你分析、记录与复盘，但不替你做投资决定。"
        if zh else
        "<b>About Trade Companion</b>\n\n"
        "Trade Companion helps you analyze, track, and review without making investment "
        "decisions for you."
    )
    return TelegramMessage(text, main_menu(language))


def feedback_categories(language: str) -> TelegramMessage:
    zh = normalize_language(language) == "zh-CN"
    return TelegramMessage(
        "请选择反馈类型：" if zh else "Choose a feedback category:",
        callback_keyboard([
            [("🐞 Bug", "feedback:BUG"),
             ("💡 功能建议" if zh else "💡 Feature Request", "feedback:FEATURE")],
            [("📈 策略建议" if zh else "📈 Strategy Suggestion", "feedback:STRATEGY")],
            [("👍 有帮助" if zh else "👍 Helpful", "feedback:HELPFUL"),
             ("👎 没帮助" if zh else "👎 Not Helpful", "feedback:NOT_HELPFUL")],
        ]),
    )


def language_picker() -> TelegramMessage:
    return TelegramMessage(
        "请选择语言 / Choose your language",
        callback_keyboard([[("中文", "language:zh-CN"), ("English", "language:en-US")]]),
    )


_HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_RULE = re.compile(r"^\s*([*_\-])(?:\s*\1){2,}\s*$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")


def _inline_markdown_to_html(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = _BOLD.sub(r"<b>\1</b>", escaped)
    escaped = _ITALIC.sub(r"<i>\1</i>", escaped)
    return escaped.replace("*", "∗")


def _render_markdown_line(line: str) -> str:
    if _RULE.match(line):
        return "────────"
    heading = _HEADING.match(line)
    if heading:
        return "<b>%s</b>" % _inline_markdown_to_html(heading.group(1))
    bullet = _BULLET.match(line)
    if bullet:
        return "• %s" % _inline_markdown_to_html(bullet.group(1))
    if line.strip().startswith("```"):
        return ""
    return _inline_markdown_to_html(line)


def render_ai_html(text: str, language: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str:
    """Convert untrusted Gemini Markdown into Telegram-safe, star-free HTML."""
    selected = normalize_language(language)
    footer = "\n\n────────\n" + html.escape(DISCLAIMER[selected], quote=False)
    budget = max(0, limit - len(footer))
    rendered: List[str] = []
    used = 0
    for raw_line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _render_markdown_line(raw_line)
        addition = line if not rendered else "\n" + line
        if used + len(addition) <= budget:
            rendered.append(line)
            used += len(addition)
            continue
        remaining = budget - used - (1 if rendered else 0)
        if remaining > 1:
            plain = html.escape(raw_line[: max(0, remaining - 1)], quote=False).replace("*", "∗")
            rendered.append(plain + "…")
        break
    body = "\n".join(rendered).strip()
    return (body + footer)[:limit]


def ai_message(text: str, language: str) -> TelegramMessage:
    return TelegramMessage(render_ai_html(text, language), main_menu(language), parse_mode="HTML")
