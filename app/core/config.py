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
    moomoo_enabled: bool = False
    moomoo_opend_host: str = "127.0.0.1"
    moomoo_opend_port: int = 11111
    moomoo_connection_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    moomoo_quote_enabled: bool = True
    moomoo_paper_account_discovery: bool = True
    moomoo_live_trading_enabled: bool = False
    moomoo_allow_order_submission: bool = False
    moomoo_security_firm: str = ""
    moomoo_preferred_market: str = "US"
    history_daily_years: int = Field(default=5, ge=1, le=20)
    history_60m_years: int = Field(default=2, ge=1, le=10)
    history_15m_days: int = Field(default=365, ge=1, le=3650)
    history_5m_days: int = Field(default=180, ge=1, le=1825)
    history_1m_days: int = Field(default=60, ge=1, le=365)
    history_adjustment_type: str = "FORWARD"
    moomoo_history_max_retries: int = Field(default=3, ge=0, le=10)
    moomoo_history_retry_delay_seconds: float = Field(default=2.0, ge=0, le=60)
    moomoo_history_request_interval_seconds: float = Field(default=0.3, ge=0, le=10)
    moomoo_history_max_pages: int = Field(default=500, ge=1, le=5000)
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
        if self.moomoo_live_trading_enabled:
            raise ValueError("Moomoo实盘交易在V1中永久禁用。")
        if self.moomoo_allow_order_submission:
            raise ValueError("Sprint 01禁止提交Moomoo订单。")
        if self.history_adjustment_type not in {"NONE", "FORWARD", "BACKWARD"}:
            raise ValueError("HISTORY_ADJUSTMENT_TYPE必须是NONE、FORWARD或BACKWARD。")
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
            "moomoo_enabled": self.moomoo_enabled,
            "moomoo_opend_host": self.moomoo_opend_host,
            "moomoo_opend_port": self.moomoo_opend_port,
            "moomoo_quote_enabled": self.moomoo_quote_enabled,
            "moomoo_paper_account_discovery": self.moomoo_paper_account_discovery,
            "moomoo_live_trading_enabled": False,
            "moomoo_allow_order_submission": False,
            "moomoo_preferred_market": self.moomoo_preferred_market,
            "telegram_enabled": self.telegram_enabled,
            "default_timezone": self.default_timezone,
            "display_timezone": self.display_timezone,
            "default_slippage_bps": self.default_slippage_bps,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
