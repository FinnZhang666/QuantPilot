from dataclasses import dataclass
from typing import Dict, List, Optional

from app.telegram_product.bot_profiles import TelegramBotProfile


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


def callback_keyboard(rows: List[List[tuple]]) -> Dict[str, object]:
    return {"inline_keyboard": [[
        {"text": label, "callback_data": "tc:" + action} for label, action in row
    ] for row in rows]}


def main_menu(profile: TelegramBotProfile) -> Dict[str, object]:
    items = list(profile.main_menu)
    return callback_keyboard([
        [(items[0].label, items[0].action), (items[1].label, items[1].action)],
        [(items[2].label, items[2].action), (items[3].label, items[3].action)],
    ])


def welcome(profile: TelegramBotProfile) -> TelegramMessage:
    return TelegramMessage(profile.welcome, main_menu(profile))


def more(language: str) -> TelegramMessage:
    zh = language == "zh-CN"
    return TelegramMessage(
        "请选择功能：" if zh else "Choose an option:",
        callback_keyboard([
            [("⭐ 我的关注" if zh else "⭐ Watchlist", "watchlist"),
             ("📊 当前持仓" if zh else "📊 Holdings", "holding")],
            [("🕘 历史记录" if zh else "🕘 History", "history"),
             ("📝 交易复盘" if zh else "📝 Reviews", "review")],
            [("💬 用户反馈" if zh else "💬 Feedback", "feedback"),
             ("🌐 切换语言" if zh else "🌐 Language", "language")],
        ]),
    )


def feedback_categories(language: str) -> TelegramMessage:
    zh = language == "zh-CN"
    return TelegramMessage(
        "请选择反馈类型：" if zh else "Choose a feedback category:",
        callback_keyboard([
            [("🐞 Bug", "feedback:BUG"), ("💡 功能建议", "feedback:FEATURE")],
            [("📈 策略建议", "feedback:STRATEGY")],
            [("👍 有帮助", "feedback:HELPFUL"), ("👎 没帮助", "feedback:NOT_HELPFUL")],
        ]),
    )


def language_picker() -> TelegramMessage:
    return TelegramMessage(
        "选择语言 / Choose language:",
        callback_keyboard([[("中文", "language:zh-CN"), ("English", "language:en-US")]]),
    )
