import re
from typing import Any, Dict

from app.core.enums import TradingMode
from app.core.exceptions import LiveTradingDisabledError

SENSITIVE_KEYS = ("token", "password", "secret", "webhook", "unlock")


def enforce_safe_trading_mode(mode: TradingMode) -> None:
    if mode == TradingMode.LIVE:
        raise LiveTradingDisabledError("Live trading is disabled in V1.")


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * max(4, len(value) - 8) + value[-4:]


def sanitize_mapping(data: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in data.items():
        if any(marker in key.lower() for marker in SENSITIVE_KEYS):
            clean[key] = mask_secret(str(value))
        elif isinstance(value, dict):
            clean[key] = sanitize_mapping(value)
        else:
            clean[key] = value
    return clean


def sanitize_text(message: str) -> str:
    return re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{16,}\b", "[REDACTED_TOKEN]", message)
