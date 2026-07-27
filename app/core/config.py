from functools import lru_cache
from typing import Any, Dict

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import TradingMode
from app.core.security import enforce_safe_trading_mode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/moomoo_quant.db"
    trading_mode: TradingMode = TradingMode.INTERNAL_PAPER
    enable_moomoo_paper: bool = False
    enable_internal_paper: bool = True
    moomoo_opend_host: str = "127.0.0.1"
    moomoo_opend_port: int = 11111
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_timeout_seconds: float = Field(default=10.0, gt=0)
    telegram_max_retries: int = Field(default=2, ge=0, le=5)
    default_timezone: str = "America/New_York"
    display_timezone: str = "Asia/Shanghai"
    default_slippage_bps: int = Field(default=8, ge=0, le=1000)
    default_portfolio_cash: float = Field(default=100000, gt=0)

    @model_validator(mode="after")
    def validate_safety(self) -> "Settings":
        enforce_safe_trading_mode(self.trading_mode)
        if self.telegram_enabled and (not self.telegram_bot_token or not self.telegram_chat_id):
            raise ValueError("Telegram is enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
        if self.trading_mode == TradingMode.MOOMOO_PAPER and not self.enable_moomoo_paper:
            raise ValueError("TRADING_MODE=MOOMOO_PAPER requires ENABLE_MOOMOO_PAPER=true.")
        return self

    def safe_dict(self) -> Dict[str, Any]:
        return {
            "app_env": self.app_env,
            "app_host": self.app_host,
            "app_port": self.app_port,
            "log_level": self.log_level,
            "database_url": self.database_url,
            "trading_mode": self.trading_mode.value,
            "enable_moomoo_paper": self.enable_moomoo_paper,
            "enable_internal_paper": self.enable_internal_paper,
            "moomoo_opend_host": self.moomoo_opend_host,
            "moomoo_opend_port": self.moomoo_opend_port,
            "telegram_enabled": self.telegram_enabled,
            "default_timezone": self.default_timezone,
            "display_timezone": self.display_timezone,
            "default_slippage_bps": self.default_slippage_bps,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
