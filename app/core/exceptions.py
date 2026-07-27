class LiveTradingDisabledError(RuntimeError):
    """Raised whenever V1 code attempts to use live trading."""


class ConfigurationError(RuntimeError):
    """Raised for human-readable application configuration failures."""
