import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_live_trading_true_fails_startup():
    with pytest.raises(ValidationError, match="永久禁用"):
        Settings(moomoo_live_trading_enabled=True, _env_file=None)


def test_order_submission_true_fails_startup():
    with pytest.raises(ValidationError, match="禁止提交"):
        Settings(moomoo_allow_order_submission=True, _env_file=None)
