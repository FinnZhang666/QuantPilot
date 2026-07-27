import re

STRATEGY_NAME = "pullback_restrength"
STRATEGY_DISPLAY_NAME = "趋势回撤后重新转强"
STRATEGY_VERSION = "1.0.0"
PARAMETER_STATUS = "UNBACKTESTED_DEFAULT"

ROLES = {
    "MARKET_BENCHMARK", "SECTOR_BENCHMARK", "TRADING",
    "RISK_INDICATOR", "PENDING_VALIDATION",
}
TEMPLATES = {
    "BROAD_MARKET", "SECTOR_ETF", "LEVERAGED_ETF",
    "INVERSE_LEVERAGED_ETF", "HIGH_GROWTH", "DEFAULT",
}
VALIDATION_STATUSES = {"VALID", "PENDING_VALIDATION", "INVALID"}
CLASSIFICATION_SOURCES = {"AUTO", "MANUAL"}
SIGNAL_TYPES = {
    "CANDIDATE_BUY", "CANDIDATE_REDUCE", "CANDIDATE_EXIT",
    "WATCH", "INSUFFICIENT_DATA", "SKIPPED",
}
SIGNAL_STATUSES = {"VALID", "WARMUP", "MISSING_FEATURE", "DISABLED", "ERROR"}
RUN_TYPES = {"FULL", "INCREMENTAL", "RANGE", "REALTIME"}
RUN_STATUSES = {"RUNNING", "SUCCESS", "PARTIAL_SUCCESS", "FAILED"}
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")

ROLE_TIMEFRAMES = {
    "TRADING": ("1m", "5m", "15m", "60m", "1d"),
    "MARKET_BENCHMARK": ("5m", "15m", "60m", "1d"),
    "SECTOR_BENCHMARK": ("5m", "15m", "60m", "1d"),
    "RISK_INDICATOR": ("5m", "15m", "60m", "1d"),
    "PENDING_VALIDATION": ("5m", "15m", "60m", "1d"),
}

KNOWN_CLASSIFICATIONS = {
    "QQQ": dict(asset_type="ETF", sector="broad-market", role="MARKET_BENCHMARK", benchmark_symbol=None, strategy_template="BROAD_MARKET"),
    "SOXX": dict(asset_type="ETF", sector="semiconductor", role="SECTOR_BENCHMARK", benchmark_symbol="QQQ", strategy_template="SECTOR_ETF"),
    "SOXL": dict(asset_type="LEVERAGED_ETF", sector="semiconductor", role="TRADING", benchmark_symbol="SOXX", strategy_template="LEVERAGED_ETF"),
    "SOXS": dict(asset_type="INVERSE_LEVERAGED_ETF", sector="semiconductor", role="RISK_INDICATOR", benchmark_symbol="SOXX", strategy_template="INVERSE_LEVERAGED_ETF"),
    "TQQQ": dict(asset_type="LEVERAGED_ETF", sector="broad-market", role="TRADING", benchmark_symbol="QQQ", strategy_template="LEVERAGED_ETF"),
    "RAM": dict(asset_type="LEVERAGED_ETF", sector="semiconductor", role="TRADING", benchmark_symbol="SOXX", strategy_template="LEVERAGED_ETF"),
    "MULL": dict(asset_type="LEVERAGED_ETF", sector="semiconductor", role="TRADING", benchmark_symbol="SOXX", strategy_template="LEVERAGED_ETF"),
    "PLTR": dict(asset_type="STOCK", sector="software-ai", role="TRADING", benchmark_symbol="QQQ", strategy_template="HIGH_GROWTH"),
    "ML": dict(asset_type="STOCK", sector="fintech", role="TRADING", benchmark_symbol="QQQ", strategy_template="HIGH_GROWTH"),
}
DEFAULT_WATCHLIST = tuple(KNOWN_CLASSIFICATIONS)

# Strategy names are mapped to the stable Sprint 04 Registry identifiers here.
FEATURE_ALIASES = {
    "ema20": "ema_20",
    "ema60": "ema_60",
    "ema20_slope": "ema20_slope_5",
    "close_vs_ema20": "close_vs_ema20_pct",
    "close_vs_ema60": "close_vs_ema60_pct",
    "rsi14": "rsi_14",
    "atr14": "atr_14",
    "atr_pct": "atr_pct_14",
    "vwap_distance": "close_vs_vwap_pct",
    "distance_high20": "distance_from_high_20_pct",
    "volume_ratio20": "volume_ratio_20",
    "close_position": "close_location_value",
    "body_ratio": "body_range_ratio",
    "return1": "return_1",
    "return5": "return_5",
}

REQUIRED_ALIASES = (
    "ema20", "ema60", "ema20_slope", "close_vs_ema20",
    "close_vs_ema60", "distance_high20", "return1", "close_position",
)
OPTIONAL_ALIASES = (
    "rsi14", "atr14", "atr_pct", "vwap_distance", "volume_ratio20",
    "body_ratio", "return5",
)
