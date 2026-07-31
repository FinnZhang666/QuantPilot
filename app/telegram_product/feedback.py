from typing import List

from app.telegram_product.i18n import translations
from app.telegram_product.models import TelegramFeedbackAction


FEEDBACK_CALLBACK_VERSION = "feedback-v1"


def feedback_menu(language: str = "zh-CN") -> List[TelegramFeedbackAction]:
    """Build the feedback information architecture without invoking Telegram Runtime."""
    text = translations(language)
    definitions = (
        ("feedback_bug", "BUG"),
        ("feedback_feature", "FEATURE"),
        ("feedback_strategy", "STRATEGY"),
        ("feedback_market", "MARKET"),
        ("feedback_other", "OTHER"),
    )
    return [
        TelegramFeedbackAction(
            label=text[label], action="submit_feedback",
            callback_data="%s:%s" % (FEEDBACK_CALLBACK_VERSION, category.lower()),
            category=category,
        )
        for label, category in definitions
    ]


def analysis_feedback_actions(
    analysis_id: int, language: str = "zh-CN",
) -> List[TelegramFeedbackAction]:
    """Return presentation-only helpful/not-helpful actions for an AI analysis."""
    if analysis_id < 1:
        raise ValueError("analysis_id必须大于0。")
    text = translations(language)
    return [
        TelegramFeedbackAction(
            text["helpful"], "analysis_feedback",
            "analysis-feedback-v1:%s:helpful" % analysis_id, "HELPFUL",
        ),
        TelegramFeedbackAction(
            text["not_helpful"], "analysis_feedback",
            "analysis-feedback-v1:%s:not-helpful" % analysis_id, "NOT_HELPFUL",
        ),
    ]
