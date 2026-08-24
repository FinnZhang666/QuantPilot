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
    gemini_api_key: str = ""
    llm_model: str = "gemini-3.1-flash-lite"
    telegram_enabled: bool = False
    telegram_runtime_enabled: bool = False
    telegram_runtime_autostart: bool = False
    telegram_registry_path: str = "config/telegram_bots.json"
    telegram_poll_timeout_seconds: int = Field(default=20, ge=1, le=50)
    telegram_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_chat_ids: str = ""
    telegram_admin_ids: str = ""
    telegram_admin_usernames: str = ""
    telegram_timeout_seconds: float = Field(default=10.0, gt=0)
    telegram_max_retries: int = Field(default=2, ge=0, le=5)
    telegram_bot_token_trade_companion_ai_en: str = ""
    telegram_bot_token_quantpilot_ai_en: str = ""
    telegram_bot_token_ai_stock_analyze_en: str = ""
    telegram_bot_token_trade_companion_zh: str = ""
    telegram_bot_token_stock_analysis_zh: str = ""
    telegram_bot_token_trade_companion_ai: str = ""
    telegram_bot_token_quantpilot_ai: str = ""
    telegram_bot_token_ai_stock_analyze: str = ""
    telegram_bot_token_jiaoyi_banlv: str = ""
    telegram_bot_token_fenxi_gupiao: str = ""
    telegram_bot_enabled_trade_companion_ai_en: bool = False
    telegram_bot_enabled_quantpilot_ai_en: bool = False
    telegram_bot_enabled_ai_stock_analyze_en: bool = False
    telegram_bot_enabled_trade_companion_zh: bool = False
    telegram_bot_enabled_stock_analysis_zh: bool = False
    universe_enabled: bool = True
    universe_auto_update_enabled: bool = True
    universe_sources_file: str = "config/universe_sources.yaml"
    universe_cache_directory: str = "data/cache/universe"
    universe_cache_ttl_hours: int = Field(default=20, ge=1, le=168)
    universe_update_interval_hours: int = Field(default=24, ge=1, le=168)
    universe_download_timeout_seconds: int = Field(default=30, ge=5, le=300)
    qmr_enabled: bool = True
    qmr_config_file: str = "config/qmr_v1.yaml"
    qmr_auto_update_enabled: bool = True
    qmr_update_interval_minutes: int = Field(default=60, ge=5, le=1440)
    recovery_enabled: bool = True
    recovery_config_file: str = "config/recovery_v1.yaml"
    recovery_auto_update_enabled: bool = True
    recovery_update_interval_minutes: int = Field(default=5, ge=1, le=1440)
    buy_score_enabled: bool = True
    buy_score_config_file: str = "config/buy_score_v1.yaml"
    buy_score_auto_update_enabled: bool = True
    qmr_backtest_enabled: bool = True
    qmr_backtest_config_file: str = "config/qmr_backtest_v1.yaml"
    default_timezone: str = "America/New_York"
    display_timezone: str = "Asia/Shanghai"
    default_slippage_bps: int = Field(default=8, ge=0, le=1000)
    default_portfolio_cash: float = Field(default=100000, gt=0)
    runtime_manager_enabled: bool = False
    paper_trading_enabled: bool = False
    paper_trading_autostart: bool = False
    paper_trading_initial_cash: float = Field(default=100000, gt=0)
    paper_trading_allow_fractional: bool = False
    paper_trading_allow_leverage: bool = False
    paper_trading_fee_per_order: float = Field(default=0, ge=0)
    paper_trading_slippage_bps: int = Field(default=8, ge=0, le=1000)
    paper_trading_position_pct: float = Field(default=0.1, gt=0, le=1)
    paper_trading_sizing_mode: str = "PERCENT_EQUITY"
    paper_trading_fixed_cash_per_trade: float = Field(default=10000, gt=0)
    paper_trading_max_position_count: int = Field(default=5, ge=1, le=100)
    paper_trading_max_entries_per_run: int = Field(default=3, ge=1, le=20)
    paper_trading_max_symbol_exposure_pct: float = Field(default=0.2, gt=0, le=1)
    paper_trading_max_strategy_exposure_pct: float = Field(default=0.5, gt=0, le=1)
    paper_trading_max_gross_exposure_pct: float = Field(default=1.0, gt=0, le=2)
    paper_trading_min_cash_reserve_pct: float = Field(default=0.1, ge=0, lt=1)
    paper_trading_allow_same_symbol_multiple: bool = False
    paper_trading_allow_strategy_coexistence: bool = False
    paper_trading_target1_reduce_pct: float = Field(default=0.5, gt=0, lt=1)
    paper_trading_max_holding_bars: int = Field(default=0, ge=0, le=10000)
    paper_trading_stale_intraday_seconds: int = Field(default=900, ge=60, le=86400)
    paper_trading_stale_daily_seconds: int = Field(default=604800, ge=86400, le=2592000)
    paper_trading_sqlite_lock_retries: int = Field(default=3, ge=0, le=10)
    paper_trading_sqlite_lock_backoff_seconds: float = Field(default=0.1, ge=0, le=5)
    paper_trading_poll_seconds: float = Field(default=60, ge=1, le=86400)
    paper_scheduler_enabled: bool = False
    review_runtime_enabled: bool = False
    strategy_scoreboard_enabled: bool = False

    @model_validator(mode="after")
    def validate_safety(self) -> "Settings":
        enforce_safe_trading_mode(self.trading_mode)
        if self.moomoo_live_trading_enabled:
            raise ValueError("Moomoo实盘交易在V1中永久禁用。")
        if self.moomoo_allow_order_submission:
            raise ValueError("Sprint 01禁止提交Moomoo订单。")
        if self.history_adjustment_type not in {"NONE", "FORWARD", "BACKWARD"}:
            raise ValueError("HISTORY_ADJUSTMENT_TYPE必须是NONE、FORWARD或BACKWARD。")
        if (
            self.telegram_enabled
            and not self.telegram_runtime_enabled
            and (not self.telegram_bot_token or not self.telegram_chat_id_list())
        ):
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
            if not (self.ai_companion_api_key or self.gemini_api_key) or not (
                self.ai_companion_model or self.llm_model
            ):
                raise ValueError("External AI Companion已启用，但缺少API Key或模型名称。")
        if self.trading_mode == TradingMode.MOOMOO_PAPER and not self.enable_moomoo_paper:
            raise ValueError("TRADING_MODE=MOOMOO_PAPER requires ENABLE_MOOMOO_PAPER=true.")
        if self.paper_trading_sizing_mode not in {"PERCENT_EQUITY", "FIXED_CASH"}:
            raise ValueError(
                "PAPER_TRADING_SIZING_MODE必须是PERCENT_EQUITY或FIXED_CASH。"
            )
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
            "telegram_runtime_enabled": self.telegram_runtime_enabled,
            "telegram_runtime_autostart": self.telegram_runtime_autostart,
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
            "runtime_manager_enabled": self.runtime_manager_enabled,
            "paper_trading_enabled": self.paper_trading_enabled,
            "paper_trading_autostart": self.paper_trading_autostart,
            "paper_scheduler_enabled": self.paper_scheduler_enabled,
            "review_runtime_enabled": self.review_runtime_enabled,
            "strategy_scoreboard_enabled": self.strategy_scoreboard_enabled,
            "universe_enabled": self.universe_enabled,
            "universe_auto_update_enabled": self.universe_auto_update_enabled,
            "universe_sources_file": self.universe_sources_file,
            "universe_cache_directory": self.universe_cache_directory,
            "qmr_enabled": self.qmr_enabled,
            "qmr_config_file": self.qmr_config_file,
            "qmr_auto_update_enabled": self.qmr_auto_update_enabled,
            "qmr_update_interval_minutes": self.qmr_update_interval_minutes,
            "recovery_enabled": self.recovery_enabled,
            "recovery_config_file": self.recovery_config_file,
            "recovery_auto_update_enabled": self.recovery_auto_update_enabled,
            "recovery_update_interval_minutes": self.recovery_update_interval_minutes,
            "buy_score_enabled": self.buy_score_enabled,
            "buy_score_config_file": self.buy_score_config_file,
            "buy_score_auto_update_enabled": self.buy_score_auto_update_enabled,
            "qmr_backtest_enabled": self.qmr_backtest_enabled,
            "qmr_backtest_config_file": self.qmr_backtest_config_file,
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
