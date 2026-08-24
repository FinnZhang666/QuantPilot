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

    def _paths(self, source):
        self.cache.mkdir(parents=True, exist_ok=True)
        identity = source.fund_symbol.lower() + "-" + source.provider.lower().replace(" ", "_")
        content_path = self.cache / (identity + "." + source.file_format)
        meta_path = self.cache / (identity + ".json")
        return content_path, meta_path

    def load_last_known_good(self, source: UniverseSource):
        content_path, meta_path = self._paths(source)
        if not content_path.exists():
            return None
        metadata = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                metadata = {}
        return content_path.read_bytes(), metadata

    def fetch_remote(self, source: UniverseSource):
        content_path, meta_path = self._paths(source)
        now = datetime.now(timezone.utc)
        response = httpx.get(source.url, timeout=self.timeout, follow_redirects=True,
                             headers={"User-Agent": "Trade Companion Universe Updater/1.0"})
        response.raise_for_status()
        content = response.content
        if not content or (source.file_format != "html" and content.lstrip().lower().startswith(b"<!doctype html")):
            raise ValueError("下载内容不是持仓文件。")
        return content, now

    def save_last_known_good(self, source: UniverseSource, content: bytes, fetched_at=None):
        content_path, meta_path = self._paths(source)
        now = fetched_at or datetime.now(timezone.utc)
        content_path.write_bytes(content)
        meta_path.write_text(json.dumps({
            "fund_symbol": source.fund_symbol, "provider": source.provider,
            "downloaded_at": now.isoformat(), "sha256": hashlib.sha256(content).hexdigest(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def fetch(self, source: UniverseSource, force: bool = False):
        """Backward-compatible fetch; new service flow uses explicit remote/LKG calls."""
        content_path, _ = self._paths(source)
        now = datetime.now(timezone.utc)
        if not force and content_path.exists():
            modified = datetime.fromtimestamp(content_path.stat().st_mtime, timezone.utc)
            if now - modified <= self.ttl:
                return content_path.read_bytes(), "FRESH_CACHE"
        try:
            content, fetched_at = self.fetch_remote(source)
            self.save_last_known_good(source, content, fetched_at)
            return content, "DOWNLOADED"
        except Exception:
            cached = self.load_last_known_good(source)
            if cached:
                return cached[0], "STALE_CACHE"
            raise
