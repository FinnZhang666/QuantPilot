import logging
from decimal import Decimal

from app.universe.config import load_sources
from app.universe.downloader import UniverseDownloader
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
        for source in self.sources:
            try:
                content, cache_status = self.downloader.fetch(source, force=force)
                records = parse_holdings(content, source.file_format)
                counts = self.repository.sync_source(source, records)
                for key in ("added", "reactivated", "inactivated"):
                    summary[key] += counts[key]
                summary["sources"].append({
                    "fund_symbol": source.fund_symbol, "provider": source.provider,
                    "records": len(records), "cache_status": cache_status, **counts,
                })
                logger.info("Universe source updated fund=%s records=%d cache=%s added=%d inactive=%d",
                            source.fund_symbol, len(records), cache_status, counts["added"], counts["inactivated"])
            except Exception as exc:
                self.db.rollback()
                summary["errors"].append({"fund_symbol": source.fund_symbol, "error": type(exc).__name__})
                logger.exception("Universe source update failed fund=%s provider=%s", source.fund_symbol, source.provider)
        status = "SUCCESS" if not summary["errors"] else ("PARTIAL_SUCCESS" if summary["sources"] else "FAILED")
        return self.repository.finish_run(run, status, summary)

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
