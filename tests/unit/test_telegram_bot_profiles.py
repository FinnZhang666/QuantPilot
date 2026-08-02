import logging
import struct
from pathlib import Path

import pytest

from app.core.config import Settings
from app.telegram_product.bot_profiles import load_bot_profiles, validate_profile
from app.telegram_product.profile_sync import TelegramProfileSynchronizer, build_sync_steps
from app.telegram_runtime.renderer import MAIN_MENU, WELCOME_TEXT


TOKENS = {
    "TELEGRAM_BOT_TOKEN_TRADE_COMPANION_AI": "test:production",
    "TELEGRAM_BOT_TOKEN_QUANTPILOT_AI": "test:reserved-1",
    "TELEGRAM_BOT_TOKEN_AI_STOCK_ANALYZE": "test:reserved-2",
    "TELEGRAM_BOT_TOKEN_JIAOYI_BANLV": "test:reserved-3",
    "TELEGRAM_BOT_TOKEN_FENXI_GUPIAO": "test:reserved-4",
}


def profiles(monkeypatch):
    for key, value in TOKENS.items():
        monkeypatch.setenv(key, value)
    return load_bot_profiles(Settings(_env_file=None))


def test_five_config_backed_profiles_are_enabled_in_one_runtime(monkeypatch):
    items = profiles(monkeypatch)
    assert len(items) == 5
    assert {item.language for item in items} == {"multi"}
    assert all(item.token for item in items)
    assert [item.alias for item in items if item.enabled] == [
        "trade_companion_ai", "quantpilot_ai", "ai_stock_analyze",
        "jiaoyi_banlv", "fenxi_gupiao",
    ]
    assert sum(item.safe_summary()["lifecycle_state"] == "PRODUCTION" for item in items) == 5
    assert all(item.token not in str(item.safe_summary()) for item in items)


def test_profiles_have_valid_commands_menu_and_square_photo(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    for item in profiles(monkeypatch):
        assert validate_profile(item, root) == []
        assert len(item.commands) == 11
        assert [entry.action for entry in item.main_menu] == [
            "analyze", "portfolio", "market", "more",
        ]
        assert {entry.action for entry in item.more_menu} >= {
            "help", "feedback", "updates", "language", "about",
        }
        assert item.welcome_uses_image is False
        assert item.profile_photo.endswith("trade-companion-logo.png")
    data = (root / profiles(monkeypatch)[0].profile_photo).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (512, 512)


def test_final_welcome_and_menu_copy_is_language_specific(monkeypatch):
    del monkeypatch
    assert "陪你走过每一次交易" in WELCOME_TEXT["zh-CN"]
    assert "不替你做决定" in WELCOME_TEXT["zh-CN"]
    assert "投资是一场长期旅程" in WELCOME_TEXT["zh-CN"]
    assert [item[0] for item in MAIN_MENU["zh-CN"]] == [
        "📈 AI分析", "💼 我的投资", "🌍 市场快照", "💡 更多",
    ]
    assert "With you through every trade" in WELCOME_TEXT["en-US"]
    assert "does not make decisions for you" in WELCOME_TEXT["en-US"]
    assert "long-term journey" in WELCOME_TEXT["en-US"]


def test_dry_run_never_calls_network_and_marks_photo_manual(monkeypatch):
    item = profiles(monkeypatch)[0]
    calls = []
    result = TelegramProfileSynchronizer(
        transport=lambda *args: calls.append(args),
    ).sync(item, dry_run=True)
    assert calls == []
    assert result["status"] == "DRY_RUN"
    assert result["alias"] == item.alias
    assert item.token not in str(result)
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
