"""Pure Telegram product presentation; it never sends messages."""

from app.telegram_product.presenter import TelegramPresenter
from app.telegram_product.feedback import analysis_feedback_actions, feedback_menu
from app.telegram_product.bot_profiles import load_bot_profiles
from app.telegram_product.profile_sync import TelegramProfileSynchronizer

__all__ = [
    "TelegramPresenter", "analysis_feedback_actions", "feedback_menu",
    "load_bot_profiles", "TelegramProfileSynchronizer",
]
