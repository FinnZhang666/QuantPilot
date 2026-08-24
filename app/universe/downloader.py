import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.universe.models import UniverseSource


class UniverseDownloader:
    def __init__(self, cache_directory: str, ttl_hours: int = 20, timeout_seconds: int = 30):
        self.cache = Path(cache_directory)
        self.ttl = timedelta(hours=ttl_hours)
        self.timeout = timeout_seconds

    def fetch(self, source: UniverseSource, force: bool = False):
        self.cache.mkdir(parents=True, exist_ok=True)
        content_path = self.cache / (source.fund_symbol.lower() + "." + source.file_format)
        meta_path = self.cache / (source.fund_symbol.lower() + ".json")
        now = datetime.now(timezone.utc)
        if not force and content_path.exists():
            modified = datetime.fromtimestamp(content_path.stat().st_mtime, timezone.utc)
            if now - modified <= self.ttl:
                return content_path.read_bytes(), "FRESH_CACHE"
        try:
            response = httpx.get(source.url, timeout=self.timeout, follow_redirects=True,
                                 headers={"User-Agent": "Trade Companion Universe Updater/1.0"})
            response.raise_for_status()
            content = response.content
            if not content or content.lstrip().lower().startswith(b"<!doctype html"):
                raise ValueError("下载内容不是持仓文件。")
            content_path.write_bytes(content)
            meta_path.write_text(json.dumps({
                "fund_symbol": source.fund_symbol, "provider": source.provider,
                "downloaded_at": now.isoformat(), "sha256": hashlib.sha256(content).hexdigest(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            return content, "DOWNLOADED"
        except Exception:
            if content_path.exists():
                return content_path.read_bytes(), "STALE_CACHE"
            raise
