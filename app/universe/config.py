from pathlib import Path
from typing import List

import yaml

from app.universe.models import UniverseSource


def load_sources(path: str) -> List[UniverseSource]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw.get("sources"), list):
        raise ValueError("Universe数据源配置缺少sources列表。")
    result = []
    for item in raw["sources"]:
        if not isinstance(item, dict) or not {"fund_symbol", "provider", "url", "format", "parser"} <= set(item):
            raise ValueError("Universe数据源配置格式无效。")
        result.append(UniverseSource(
            fund_symbol=str(item["fund_symbol"]).strip().upper(),
            provider=str(item["provider"]).strip(), url=str(item["url"]).strip(),
            file_format=str(item["format"]).strip().lower(), parser=str(item["parser"]).strip(),
            enabled=bool(item.get("enabled", True)),
        ))
    funds = [item.fund_symbol for item in result if item.enabled]
    if len(funds) != len(set(funds)):
        raise ValueError("Universe数据源fund_symbol重复。")
    return result
