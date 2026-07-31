from dataclasses import replace

import pytest

from app.symbol_overview.service import SymbolOverviewService
from app.telegram_product.deep_links import deep_link
from app.telegram_product.feedback import analysis_feedback_actions, feedback_menu
from app.telegram_product.formatter import TelegramFormatter
from app.telegram_product.presenter import MAX_MESSAGE_LENGTH, TelegramPresenter
from tests.unit.test_market_snapshot import add_market, add_plan, add_portfolio
from app.portfolio_center.service import HoldingService


def overview(db, symbol="SOXL", with_objects=False):
    add_market(db, symbol)
    if with_objects:
        plan = add_plan(db, symbol)
        portfolio = add_portfolio(db)
        HoldingService(db).open_holding(
            portfolio.id, symbol, "US", "LONG", "3", "28.50", trade_plan_id=plan.id,
        )
    return SymbolOverviewService(db).get(symbol)


def test_view_model_is_derived_from_symbol_overview(db):
    value = TelegramPresenter().symbol_overview(overview(db, with_objects=True))
    assert value.schema_version == "telegram-symbol-overview-v1"
    assert value.symbol == "SOXL" and len(value.sections) == 5
    assert any(button.action == "view_holding" and button.enabled for button in value.buttons)


@pytest.mark.parametrize("language,expected", [("zh-CN", "市场快照"), ("en-US", "Market Snapshot")])
def test_internationalized_message(db, language, expected):
    value = overview(db)
    result = TelegramFormatter().overview(value, language)
    assert expected in result["message"] and result["sent"] is False


def test_invalid_language_is_rejected(db):
    with pytest.raises(ValueError, match="language"):
        TelegramPresenter().symbol_overview(overview(db), "fr-FR")


def test_empty_related_objects_become_disabled_buttons(db):
    result = TelegramFormatter().overview(overview(db))
    buttons = {row["action"]: row for row in result["buttons"]}
    assert buttons["view_snapshot"]["enabled"] is True
    assert buttons["view_ai"]["enabled"] is False


def test_deep_link_encoding_and_validation():
    assert deep_link("symbol", "BRK B").endswith("BRK%20B")
    with pytest.raises(ValueError):
        deep_link("order", "SOXL")


def test_markdown_unicode_decimal_are_safe(db):
    value = overview(db, "QQQ")
    value = replace(value, symbol="测_试", snapshot=replace(value.snapshot, symbol="测_试"))
    result = TelegramFormatter().overview(value)
    assert "测\\_试" in result["message"]
    assert "32\\.15" in result["message"]


def test_message_length_is_bounded(db):
    value = overview(db)
    view_model = TelegramPresenter().symbol_overview(value)
    sections = list(view_model.sections)
    sections[-1] = {"title": "AI", "value": "很长" * 3000}
    text = TelegramPresenter().format(replace(view_model, sections=sections))
    assert len(text) <= MAX_MESSAGE_LENGTH and text.endswith("不构成新的交易信号。")


def test_formatter_facade_reuses_snapshot_formatter(db):
    value = overview(db)
    assert "Market Snapshot" in TelegramFormatter.snapshot(value.snapshot)


def test_presentation_does_not_mutate_session(db):
    value = overview(db)
    before = len(db.new), len(db.dirty), len(db.deleted)
    TelegramFormatter().overview(value)
    assert before == (len(db.new), len(db.dirty), len(db.deleted))


def test_feedback_menu_is_presentation_only_and_bilingual():
    zh = feedback_menu("zh-CN")
    en = feedback_menu("en-US")
    assert [item.category for item in zh] == ["BUG", "FEATURE", "STRATEGY", "MARKET", "OTHER"]
    assert zh[0].label == "🐞 Bug"
    assert en[1].label == "💡 Feature Idea"
    assert all(item.action == "submit_feedback" for item in zh)
    assert all(item.callback_data.startswith("feedback-v1:") for item in zh)


def test_ai_analysis_feedback_actions_are_safe_models():
    actions = analysis_feedback_actions(12, "zh-CN")
    assert [item.category for item in actions] == ["HELPFUL", "NOT_HELPFUL"]
    assert actions[0].callback_data == "analysis-feedback-v1:12:helpful"
    assert actions[1].callback_data == "analysis-feedback-v1:12:not-helpful"
    assert not hasattr(actions[0], "send")


def test_ai_analysis_feedback_rejects_invalid_id():
    with pytest.raises(ValueError):
        analysis_feedback_actions(0)
