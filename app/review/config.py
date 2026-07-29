from datetime import timedelta
from pathlib import Path
from typing import Dict

import yaml


def load_review_windows(path: str) -> Dict[str, object]:
    location = Path(path)
    if not location.is_absolute():
        location = Path(__file__).resolve().parents[2] / location
    payload = yaml.safe_load(location.read_text(encoding="utf-8")) or {}
    windows = payload.get("windows") or []
    parsed = {str(item).lower(): parse_window(str(item)) for item in windows}
    if not parsed:
        raise ValueError("Review Window配置不能为空。")
    return {"version": str(payload.get("version", "1.0.0")), "windows": parsed}


def parse_window(value: str) -> timedelta:
    normalized = value.strip().lower()
    if normalized.endswith("h"):
        amount = int(normalized[:-1])
        return timedelta(hours=amount)
    if normalized.endswith("d"):
        amount = int(normalized[:-1])
        return timedelta(days=amount)
    raise ValueError("不支持的Review Window：%s" % value)
