import logging
from pathlib import Path

import pytest

from app.core.config import Settings
from app.telegram_product.bot_profiles import load_bot_profiles, validate_profile
from app.telegram_product.profile_sync import TelegramProfileSynchronizer, build_sync_steps


TOKENS = {
    "TELEGRAM_BOT_TOKEN_TRADE_COMPANION_AI_EN": "test:english-primary",
    "TELEGRAM_BOT_TOKEN_QUANTPILOT_AI_EN": "test:english-legacy",
    "TELEGRAM_BOT_TOKEN_AI_STOCK_ANALYZE_EN": "test:english-analysis",
    "TELEGRAM_BOT_TOKEN_TRADE_COMPANION_ZH": "test:chinese-primary",
    "TELEGRAM_BOT_TOKEN_STOCK_ANALYSIS_ZH": "test:chinese-analysis",
}


def profiles(monkeypatch):
    for key, value in TOKENS.items():
        monkeypatch.setenv(key, value)
    return load_bot_profiles(Settings(_env_file=None))


def test_five_bot_profiles_load_without_exposing_tokens(monkeypatch):
    items = profiles(monkeypatch)
    assert len(items) == 5
    assert {item.language for item in items} == {"zh-CN", "en-US"}
    assert all(item.token for item in items)
    assert all(item.token not in str(item.safe_summary()) for item in items)
    assert not any(item.enabled for item in items)


def test_profiles_have_valid_commands_copy_menu_and_photo(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    for item in profiles(monkeypatch):
        assert validate_profile(item, root) == []
        assert len(item.commands) == 8
        assert [entry.action for entry in item.main_menu] == [
            "analyze", "portfolio", "market", "more",
        ]
        assert len(item.more_menu) == 5
        assert item.welcome_uses_image is False
        assert "Trade Companion" in item.welcome
        assert "guaranteed" not in item.welcome.lower()


def test_final_start_copy_is_language_specific(monkeypatch):
    items = profiles(monkeypatch)
    chinese = next(item for item in items if item.language == "zh-CN")
    english = next(item for item in items if item.language == "en-US")
    assert "👋 欢迎来到 Trade Companion" in chinese.welcome
    assert "不替你做决定" in chinese.welcome
    assert "投资是一场长期旅程" in chinese.welcome
    assert "👋 Welcome to Trade Companion" in english.welcome
    assert "doesn’t replace your decisions" in english.welcome
    assert "Investing is a long journey" in english.welcome


def test_dry_run_never_calls_network_and_marks_photo_manual(monkeypatch):
    item = profiles(monkeypatch)[0]
    calls = []
    result = TelegramProfileSynchronizer(
        transport=lambda *args: calls.append(args),
    ).sync(item, dry_run=True)
    assert calls == []
    assert result["status"] == "DRY_RUN"
    assert result["alias"] == item.alias
    assert not any(item.token in str(value) for value in result.values())
    photo = next(step for step in result["steps"] if step["method"] == "setProfilePhoto")
    assert photo["status"] == "MANUAL_REQUIRED"


def test_sync_plan_contains_supported_official_methods(monkeypatch):
    methods = [item.method for item in build_sync_steps(profiles(monkeypatch)[0])]
    assert methods == [
        "getMe", "setMyName", "setMyShortDescription", "setMyDescription",
        "setMyCommands", "setChatMenuButton", "setProfilePhoto",
    ]


def test_sync_log_never_contains_token(monkeypatch, caplog):
    item = profiles(monkeypatch)[0]
    with caplog.at_level(logging.INFO):
        TelegramProfileSynchronizer().sync(item, dry_run=True)
    assert item.token not in caplog.text


def test_apply_failure_masks_token(monkeypatch):
    item = profiles(monkeypatch)[0]

    def fail(*args):
        raise RuntimeError("safe transport failure")

    with pytest.raises(RuntimeError, match="safe transport failure") as error:
        TelegramProfileSynchronizer(transport=fail).sync(item, dry_run=False)
    assert item.token not in str(error.value)
