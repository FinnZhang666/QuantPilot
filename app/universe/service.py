import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from app.universe.config import load_sources
from app.universe.downloader import UniverseDownloader
from app.universe.models import UniverseFetchResult
from app.universe.parser import parse_holdings, normalize_symbol
from app.universe.repository import UniverseRepository

logger = logging.getLogger("trade_companion.universe")


class UniverseService:
    def __init__(self, db, settings, downloader=None):
        self.db = db
        self.settings = settings
        self.repository = UniverseRepository(db)
        self.sources = [item for item in load_sources(settings.universe_sources_file) if item.enabled]
        self.downloader = downloader or UniverseDownloader(
            settings.universe_cache_directory, settings.universe_cache_ttl_hours,
            settings.universe_download_timeout_seconds,
        )

    def update(self, force=False):
        run = self.repository.create_run([{"fund_symbol": s.fund_symbol, "provider": s.provider} for s in self.sources])
        summary = {"added": 0, "reactivated": 0, "inactivated": 0, "sources": [], "errors": []}
        grouped = defaultdict(list)
        for source in self.sources:
            grouped[source.fund_symbol].append(source)
        for fund_symbol, sources in sorted(grouped.items()):
            try:
                fetched = self._fetch_group(sorted(sources, key=lambda item: (item.priority, item.role)))
                source = next(item for item in sources if item.provider == fetched.source_name)
                if fetched.cache_used:
                    summary["sources"].append(self._source_summary(fetched, None, sources))
                    summary["errors"].append({"fund_symbol": fund_symbol,
                                              "error": fetched.error_code or "USING_LAST_KNOWN_GOOD"})
                    logger.warning("Universe using LKG fund=%s source=%s members=%d",
                                   fund_symbol, fetched.source_name, len(fetched.members))
                    continue
                counts = self.repository.sync_source(source, fetched.members)
                for key in ("added", "reactivated", "inactivated"):
                    summary[key] += counts[key]
                summary["sources"].append(self._source_summary(fetched, counts, sources))
                logger.info("Universe source updated fund=%s records=%d source=%s fallback=%s added=%d inactive=%d",
                            fund_symbol, len(fetched.members), fetched.source_name,
                            fetched.fallback_used, counts["added"], counts["inactivated"])
            except Exception as exc:
                self.db.rollback()
                summary["errors"].append({"fund_symbol": fund_symbol, "error": type(exc).__name__})
                logger.exception("Universe source update failed fund=%s", fund_symbol)
        status = "SUCCESS" if not summary["errors"] else ("PARTIAL_SUCCESS" if summary["sources"] else "FAILED")
        return self.repository.finish_run(run, status, summary)

    def _fetch_group(self, sources):
        failures = []
        now = datetime.now(timezone.utc)
        for index, source in enumerate(sources):
            try:
                if hasattr(self.downloader, "fetch_remote"):
                    content, fetched_at = self.downloader.fetch_remote(source)
                else:
                    content, _ = self.downloader.fetch(source, force=True)
                    fetched_at = now
                records = parse_holdings(content, source.file_format)
                if not records:
                    raise ValueError("EMPTY_UNIVERSE_SNAPSHOT")
                if hasattr(self.downloader, "save_last_known_good"):
                    self.downloader.save_last_known_good(source, content, fetched_at)
                return UniverseFetchResult(source.fund_symbol, source.provider, source.source_type,
                    records, fetched_at, fetched_at, True, "FRESH", "HIGH",
                    fallback_used=index > 0)
            except Exception as exc:
                failures.append("%s:%s" % (source.provider, type(exc).__name__))
        for source in sources:
            cached = self.downloader.load_last_known_good(source) if hasattr(self.downloader, "load_last_known_good") else None
            if not cached:
                continue
            content, metadata = cached
            records = parse_holdings(content, source.file_format)
            if not records:
                continue
            fetched_at = metadata.get("downloaded_at")
            try:
                fetched_at = datetime.fromisoformat(fetched_at) if fetched_at else now
            except ValueError:
                fetched_at = now
            return UniverseFetchResult(source.fund_symbol, source.provider, source.source_type,
                records, fetched_at, fetched_at, True, "STALE", "LOW",
                fallback_used=len(sources) > 1, cache_used=True,
                error_code="REMOTE_SOURCES_FAILED", error_message=";".join(failures))
        raise RuntimeError("ALL_UNIVERSE_SOURCES_FAILED:" + ";".join(failures))

    @staticmethod
    def _source_summary(result, counts, sources):
        counts = counts or {"added": 0, "reactivated": 0, "inactivated": 0}
        primary = next((item.provider for item in sources if item.role == "PRIMARY"), None)
        fallbacks = [item.provider for item in sources if item.role == "FALLBACK"]
        return {
            "fund_symbol": result.universe_code,
            "primary_source": primary,
            "fallback_source": fallbacks[0] if fallbacks else None,
            "actual_source": result.source_name,
            "source_type": result.source_type,
            "member_count": len(result.members),
            "records": len(result.members),
            "added": counts["added"], "reactivated": counts["reactivated"],
            "removed": counts["inactivated"], "unchanged": max(0, len(result.members) - counts["added"] - counts["reactivated"]),
            "fetched_at": result.fetched_at.isoformat(), "effective_at": result.effective_at.isoformat(),
            "data_quality": result.quality, "freshness": result.freshness,
            "fallback_used": result.fallback_used, "cache_used": result.cache_used,
            "failure_reason": result.error_message,
        }

    def list(self, **kwargs):
        rows, total = self.repository.list(**kwargs)
        memberships = self.repository.memberships([row.id for row in rows])
        return [self.serialize(row, memberships.get(row.id, [])) for row in rows], total

    def get(self, symbol):
        row = self.repository.get(normalize_symbol(symbol))
        if row is None:
            return None
        return self.serialize(row, self.repository.memberships([row.id])[row.id])

    @staticmethod
    def serialize(row, memberships):
        active = {item.fund_symbol: item for item in memberships if item.is_active}
        def decimal(value):
            return str(value) if isinstance(value, Decimal) or value is not None else None
        return {
            "id": row.id, "symbol": row.symbol, "market": row.market,
            "company_name": row.company_name, "sector": row.sector,
            "industry": row.industry, "market_cap": decimal(row.market_cap),
            "qqq_member": "QQQ" in active, "spy_member": "SPY" in active,
            "qqq_weight": decimal(active["QQQ"].weight) if "QQQ" in active else None,
            "spy_weight": decimal(active["SPY"].weight) if "SPY" in active else None,
            "memberships": [{"fund_symbol": item.fund_symbol, "weight": decimal(item.weight)} for item in active.values()],
            "first_seen": row.first_seen, "last_update": row.last_update, "status": row.status,
        }
