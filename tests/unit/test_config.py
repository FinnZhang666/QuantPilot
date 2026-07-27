import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.enums import TradingMode
from app.core.exceptions import LiveTradingDisabledError


def test_config_loads_defaults():
    settings = Settings(_env_file=None)
    assert settings.trading_mode == TradingMode.INTERNAL_PAPER


def test_live_mode_startup_fails():
    with pytest.raises(LiveTradingDisabledError):
        Settings(trading_mode="LIVE", _env_file=None)


def test_telegram_disabled_does_not_require_token():
    assert Settings(telegram_enabled=False, _env_file=None).telegram_bot_token == ""


def test_telegram_enabled_without_token_fails():
    with pytest.raises(ValidationError, match="TELEGRAM_BOT_TOKEN"):
        Settings(telegram_enabled=True, _env_file=None)
