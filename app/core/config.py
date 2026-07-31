from functools import lru_cache
from typing import Any, Dict, List

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
    log_directory: str = "logs"
    log_max_bytes: int = Field(default=5_000_000, ge=100_000)
    log_backup_count: int = Field(default=5, ge=1, le=100)
    log_json_enabled: bool = True
    backup_directory: str = "backups"
    backup_daily_retention: int = Field(default=7, ge=1, le=365)
    backup_weekly_retention: int = Field(default=4, ge=1, le=52)
    database_url: str = "sqlite:///./data/quantpilot.db"
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
    realtime_symbols: str = (
        "US.SOXL,US.MULL,US.TQQQ,US.NVDL,US.RAM,US.QQQ,"
        "US.SPY,US.SMH,US.SOXX,US.NVDA,US.AMD,US.MU"
    )
    realtime_batch_size: int = Field(default=200, ge=1, le=5000)
    realtime_flush_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    realtime_queue_max_size: int = Field(default=10000, ge=100, le=1000000)
    realtime_stale_seconds_regular: int = Field(default=30, ge=5, le=3600)
    realtime_stale_seconds_extended: int = Field(default=120, ge=10, le=7200)
    realtime_reconnect_max_attempts: int = Field(default=5, ge=0, le=20)
    realtime_reconnect_delay_seconds: float = Field(default=5.0, ge=0, le=300)
    realtime_health_check_interval_seconds: float = Field(default=10.0, ge=1, le=300)
    realtime_ticker_retention_days: int = Field(default=30, ge=1, le=3650)
    realtime_quote_retention_days: int = Field(default=90, ge=1, le=3650)
    realtime_bar_retention_days: int = Field(default=365, ge=1, le=3650)
    feature_read_chunk_size: int = Field(default=10000, ge=100, le=100000)
    feature_write_batch_size: int = Field(default=1000, ge=100, le=5000)
    feature_max_workers: int = Field(default=1, ge=1, le=4)
    moomoo_strategy_auto_calculate_features: bool = True
    moomoo_warn_free_disk_gb: float = Field(default=15.0, ge=0)
    moomoo_min_free_disk_gb: float = Field(default=10.0, ge=0)
    strategy_read_chunk_size: int = Field(default=5000, ge=100, le=20000)
    strategy_max_estimated_bars: int = Field(default=100000, ge=1000)
    realtime_runtime_enabled: bool = False
    realtime_timeframes: str = "1m"
    opportunity_min_score: int = Field(default=70, ge=0, le=100)
    opportunity_default_expiry_bars: int = Field(default=3, ge=1, le=100)
    runtime_poll_interval_seconds: float = Field(default=2.0, ge=0.1, le=60)
    dashboard_admin_token: str = ""
    dashboard_readonly_public: bool = False
    market_regime_enabled: bool = True
    market_regime_timeframe: str = "1d"
    market_regime_benchmark: str = "QQQ"
    market_regime_sector_benchmark: str = "SOXX"
    market_regime_risk_symbol: str = "SOXS"
    market_regime_min_bars: int = Field(default=120, ge=20, le=1000)
    market_regime_cache_minutes: int = Field(default=30, ge=1, le=1440)
    candidate_pool_enabled: bool = True
    candidate_pool_max_total: int = Field(default=200, ge=1, le=5000)
    candidate_pool_max_long: int = Field(default=120, ge=1, le=5000)
    candidate_pool_max_short: int = Field(default=120, ge=1, le=5000)
    candidate_pool_min_score: int = Field(default=60, ge=0, le=100)
    candidate_pool_both_score_gap: int = Field(default=5, ge=0, le=100)
    candidate_pool_expiry_hours: int = Field(default=36, ge=1, le=720)
    candidate_pool_daily_enabled: bool = False
    candidate_pool_daily_time: str = "08:00"
    candidate_pool_timezone: str = "America/New_York"
    candidate_pool_config_universe_file: str = "config/candidate_universe.yaml"
    opportunity_review_enabled: bool = True
    opportunity_review_windows_file: str = "config/review_windows_v1.yaml"
    opportunity_review_batch_size: int = Field(default=100, ge=1, le=1000)
    opportunity_review_poll_seconds: int = Field(default=300, ge=10, le=86400)
    ai_review_enabled: bool = False
    ai_review_provider: str = "mock"
    ai_review_base_url: str = ""
    ai_review_api_key: str = ""
    ai_review_model: str = ""
    ai_review_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    ai_review_max_retries: int = Field(default=2, ge=0, le=10)
    ai_review_batch_size: int = Field(default=20, ge=1, le=200)
    ai_review_min_window: str = "1D"
    ai_review_prompt_version: str = "v1"
    ai_review_store_raw_response: bool = True
    ai_review_auto_run: bool = False
    ai_review_admin_only: bool = True
    ai_companion_enabled: bool = False
    ai_companion_provider: str = "mock"
    ai_companion_model: str = "mock-companion-v1"
    ai_companion_api_key: str = ""
    ai_companion_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    ai_companion_max_retries: int = Field(default=1, ge=0, le=10)
    ai_companion_max_output_tokens: int = Field(default=2048, ge=128, le=32768)
    ai_companion_default_language: str = "zh-CN"
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_chat_ids: str = ""
    telegram_admin_ids: str = ""
    telegram_admin_usernames: str = ""
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
        if self.telegram_enabled and (not self.telegram_bot_token or not self.telegram_chat_id_list()):
            raise ValueError("Telegram已启用，但缺少TELEGRAM_BOT_TOKEN或TELEGRAM_CHAT_IDS。")
        if self.ai_review_provider not in {"mock", "openai_compatible", "local"}:
            raise ValueError("AI_REVIEW_PROVIDER必须是mock、openai_compatible或local。")
        if self.ai_review_enabled and self.ai_review_provider != "mock":
            if not self.ai_review_base_url or not self.ai_review_model:
                raise ValueError("AI Review已启用，但缺少Base URL或模型名称。")
        if self.ai_companion_provider not in {"mock", "gemini"}:
            raise ValueError("AI_COMPANION_PROVIDER必须是mock或gemini。")
        if self.ai_companion_default_language not in {"zh-CN", "en-US"}:
            raise ValueError("AI_COMPANION_DEFAULT_LANGUAGE必须是zh-CN或en-US。")
        if self.ai_companion_enabled and self.ai_companion_provider != "mock":
            if not self.ai_companion_api_key or not self.ai_companion_model:
                raise ValueError("External AI Companion已启用，但缺少API Key或模型名称。")
        if self.trading_mode == TradingMode.MOOMOO_PAPER and not self.enable_moomoo_paper:
            raise ValueError("TRADING_MODE=MOOMOO_PAPER requires ENABLE_MOOMOO_PAPER=true.")
        return self

    def safe_dict(self) -> Dict[str, Any]:
        return {
            "app_env": self.app_env,
            "app_host": self.app_host,
            "app_port": self.app_port,
            "log_level": self.log_level,
            "log_directory": self.log_directory,
            "log_json_enabled": self.log_json_enabled,
            "backup_directory": self.backup_directory,
            "backup_daily_retention": self.backup_daily_retention,
            "backup_weekly_retention": self.backup_weekly_retention,
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
            "ai_review_enabled": self.ai_review_enabled,
            "ai_review_provider": self.ai_review_provider,
            "ai_review_model": self.ai_review_model,
            "ai_companion_enabled": self.ai_companion_enabled,
            "ai_companion_provider": self.ai_companion_provider,
            "ai_companion_model": self.ai_companion_model,
            "ai_companion_default_language": self.ai_companion_default_language,
            "default_timezone": self.default_timezone,
            "display_timezone": self.display_timezone,
            "default_slippage_bps": self.default_slippage_bps,
        }

    def realtime_symbol_list(self) -> List[str]:
        return list(dict.fromkeys(
            value.strip().upper()
            for value in self.realtime_symbols.split(",")
            if value.strip()
        ))

    def realtime_timeframe_list(self) -> List[str]:
        allowed = {"1m", "5m", "15m", "30m", "60m", "1d"}
        values = list(dict.fromkeys(
            value.strip() for value in self.realtime_timeframes.split(",") if value.strip()
        ))
        invalid = [value for value in values if value not in allowed]
        if invalid:
            raise ValueError("REALTIME_TIMEFRAMES包含无效周期：" + "、".join(invalid))
        return values

    def telegram_chat_id_list(self) -> List[str]:
        source = self.telegram_chat_ids or self.telegram_chat_id
        return list(dict.fromkeys(value.strip() for value in source.split(",") if value.strip()))

    def telegram_admin_id_set(self) -> set:
        return {value.strip() for value in self.telegram_admin_ids.split(",") if value.strip()}

    def telegram_admin_username_set(self) -> set:
        return {
            value.strip().lstrip("@").lower()
            for value in self.telegram_admin_usernames.split(",")
            if value.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
