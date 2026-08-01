from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from app.core.config import Settings


@dataclass(frozen=True)
class BotCommand:
    command: str
    description: str


@dataclass(frozen=True)
class BotMenuItem:
    label: str
    action: str


@dataclass(frozen=True)
class TelegramBotProfile:
    alias: str
    purpose: str
    language: str
    market_scope: str
    display_name: str
    short_description: str
    description: str
    welcome: str
    commands: Tuple[BotCommand, ...]
    main_menu: Tuple[BotMenuItem, ...]
    more_menu: Tuple[BotMenuItem, ...]
    profile_photo: str
    welcome_uses_image: bool
    token: str
    enabled: bool

    def safe_summary(self) -> Dict[str, object]:
        return {
            "alias": self.alias, "purpose": self.purpose,
            "language": self.language, "market_scope": self.market_scope,
            "display_name": self.display_name, "enabled": self.enabled,
            "token_configured": bool(self.token), "profile_photo": self.profile_photo,
            "welcome_uses_image": self.welcome_uses_image,
        }


ZH_COMMANDS = (
    BotCommand("start", "开始使用"), BotCommand("analyze", "分析股票"),
    BotCommand("watchlist", "我的关注"), BotCommand("portfolio", "我的投资"),
    BotCommand("market", "市场快照"), BotCommand("help", "使用帮助"),
    BotCommand("feedback", "提交建议"), BotCommand("language", "切换语言"),
)
EN_COMMANDS = (
    BotCommand("start", "Start"), BotCommand("analyze", "Analyze a stock"),
    BotCommand("watchlist", "My watchlist"), BotCommand("portfolio", "My investments"),
    BotCommand("market", "Market snapshot"), BotCommand("help", "Help"),
    BotCommand("feedback", "Send feedback"), BotCommand("language", "Change language"),
)
ZH_MAIN_MENU = (
    BotMenuItem("📈 AI分析", "analyze"), BotMenuItem("💼 我的投资", "portfolio"),
    BotMenuItem("🌍 市场快照", "market"), BotMenuItem("💡 更多", "more"),
)
EN_MAIN_MENU = (
    BotMenuItem("📈 AI Analysis", "analyze"), BotMenuItem("💼 My Investments", "portfolio"),
    BotMenuItem("🌍 Market Snapshot", "market"), BotMenuItem("💡 More", "more"),
)
ZH_MORE_MENU = (
    BotMenuItem("关于我们", "about"), BotMenuItem("使用帮助", "help"),
    BotMenuItem("提交建议", "feedback"), BotMenuItem("更新日志", "changelog"),
    BotMenuItem("切换语言", "language"),
)
EN_MORE_MENU = (
    BotMenuItem("About", "about"), BotMenuItem("Help", "help"),
    BotMenuItem("Send Feedback", "feedback"), BotMenuItem("Changelog", "changelog"),
    BotMenuItem("Change Language", "language"),
)

ZH_WELCOME = """👋 欢迎来到 Trade Companion

陪你走过每一次交易，而不是只推送一个买卖点。

无论你是刚开始投资，还是已经拥有自己的交易体系，我都会帮助你：

📈 发现值得关注的交易机会
🧠 理解市场，而不仅仅是看到涨跌
📋 制定并跟踪交易计划
💼 管理你的投资与持仓
🔔 在关键时刻提醒你
📊 与你一起复盘每一次交易，不断优化策略

Trade Companion 不替你做决定，只帮助你做出更好的决定。

投资是一场长期旅程，我会一直陪伴你。

请选择下面开始。"""

EN_WELCOME = """👋 Welcome to Trade Companion

With you through every trade, not just another buy or sell signal.

I’ll help you:

📈 Discover new opportunities
🧠 Understand the market
📋 Build better trade plans
💼 Track your investments
🔔 Stay informed at the right time
📊 Review every trade and continuously improve

Trade Companion doesn’t replace your decisions. It helps you make better ones.

Investing is a long journey. I’ll be with you every step of the way.

Choose where to start."""


def _profile(alias, purpose, language, market_scope, token, enabled):
    chinese = language == "zh-CN"
    return TelegramBotProfile(
        alias=alias, purpose=purpose, language=language, market_scope=market_scope,
        display_name="Trade Companion",
        short_description=("AI 交易分析、计划跟踪与持仓陪伴" if chinese else
                           "AI trade analysis, planning and position companion"),
        description=(
            "提供市场分析、关注股票、交易计划、AI 解读、关键提醒与交易反馈。"
            "不替你做决定，只帮助你做出更好的决定。"
            if chinese else
            "Market analysis, watchlists, trade plans, AI explanations, alerts, and feedback. "
            "It does not replace your decisions; it helps you make better ones."
        ),
        welcome=ZH_WELCOME if chinese else EN_WELCOME,
        commands=ZH_COMMANDS if chinese else EN_COMMANDS,
        main_menu=ZH_MAIN_MENU if chinese else EN_MAIN_MENU,
        more_menu=ZH_MORE_MENU if chinese else EN_MORE_MENU,
        profile_photo="app/dashboard/static/branding/trade-companion-logo-en.png",
        welcome_uses_image=False,
        token=token, enabled=enabled,
    )


def load_bot_profiles(settings: Settings) -> List[TelegramBotProfile]:
    return [
        _profile("trade_companion_ai_en", "primary_english_companion", "en-US", "US",
                 settings.telegram_bot_token_trade_companion_ai_en,
                 settings.telegram_bot_enabled_trade_companion_ai_en),
        _profile("quantpilot_ai_en", "legacy_english_companion", "en-US", "US",
                 settings.telegram_bot_token_quantpilot_ai_en,
                 settings.telegram_bot_enabled_quantpilot_ai_en),
        _profile("ai_stock_analyze_en", "english_stock_analysis", "en-US", "US",
                 settings.telegram_bot_token_ai_stock_analyze_en,
                 settings.telegram_bot_enabled_ai_stock_analyze_en),
        _profile("trade_companion_zh", "primary_chinese_companion", "zh-CN", "US",
                 settings.telegram_bot_token_trade_companion_zh,
                 settings.telegram_bot_enabled_trade_companion_zh),
        _profile("stock_analysis_zh", "chinese_stock_analysis", "zh-CN", "US",
                 settings.telegram_bot_token_stock_analysis_zh,
                 settings.telegram_bot_enabled_stock_analysis_zh),
    ]


def validate_profile(profile: TelegramBotProfile, repository_root: Path) -> List[str]:
    errors = []
    if len(profile.short_description) > 120:
        errors.append("short_description_too_long")
    if len(profile.description) > 512:
        errors.append("description_too_long")
    if len(profile.welcome) > 4096:
        errors.append("welcome_too_long")
    if any(not item.command.islower() or len(item.command) > 32 for item in profile.commands):
        errors.append("invalid_command")
    if any(len(item.description) > 256 for item in profile.commands):
        errors.append("command_description_too_long")
    if len(profile.main_menu) != 4:
        errors.append("invalid_main_menu")
    if not (repository_root / profile.profile_photo).is_file():
        errors.append("profile_photo_missing")
    return errors
