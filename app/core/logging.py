import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

from app.core.security import sanitize_mapping, sanitize_text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "event": getattr(record, "event", "log"),
            "message": sanitize_text(record.getMessage()),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload.update(sanitize_mapping(context))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level.upper())
    if getattr(root, "_quantpilot_configured", False):
        return
    formatter = JsonFormatter()
    app_handler = RotatingFileHandler("logs/app.log", maxBytes=5_000_000, backupCount=5)
    app_handler.setFormatter(formatter)
    error_handler = RotatingFileHandler("logs/error.log", maxBytes=5_000_000, backupCount=5)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(console)
    root._quantpilot_configured = True  # type: ignore[attr-defined]
