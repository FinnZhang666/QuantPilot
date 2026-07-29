from pathlib import Path
from typing import Iterable, List

import yaml
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.candidate_pool.models import UniverseSymbol
from app.database.models import CandidatePoolEntry, WatchlistItem


class WatchlistUniverseProvider:
    def __init__(self, db: Session):
        self.db = db

    def get_symbols(self) -> List[UniverseSymbol]:
        return [
            UniverseSymbol(
                row.symbol, row.market, row.asset_type, "WATCHLIST",
                row.sector, row.benchmark_symbol,
            )
            for row in self.db.scalars(select(WatchlistItem).where(
                WatchlistItem.enabled.is_(True),
            ).order_by(WatchlistItem.symbol))
        ]


class ConfigUniverseProvider:
    def __init__(self, path: str):
        self.path = path

    def get_symbols(self) -> List[UniverseSymbol]:
        source = yaml.safe_load(Path(self.path).read_text(encoding="utf-8")) or {}
        return [UniverseSymbol(str(value).upper().replace("US.", ""), source="SYSTEM")
                for value in source.get("symbols", [])]


class PreviousCandidateUniverseProvider:
    def __init__(self, db: Session):
        self.db = db

    def get_symbols(self) -> List[UniverseSymbol]:
        rows = self.db.scalars(select(CandidatePoolEntry).order_by(
            desc(CandidatePoolEntry.pool_date),
        ).limit(500)).all()
        return [
            UniverseSymbol(row.symbol, row.market, row.asset_type, "PREVIOUS_CANDIDATE",
                           benchmark=row.benchmark_symbol)
            for row in rows
        ]


class CombinedUniverseProvider:
    def __init__(self, providers: Iterable[object]):
        self.providers = providers

    def get_symbols(self) -> List[UniverseSymbol]:
        merged = {}
        sources = {}
        for provider in self.providers:
            for item in provider.get_symbols():
                key = (item.market, item.symbol)
                merged.setdefault(key, item)
                sources.setdefault(key, []).append(item.source)
        return [
            UniverseSymbol(
                item.symbol, item.market, item.asset_type,
                ",".join(sorted(set(sources[key]))), item.sector, item.benchmark,
            )
            for key, item in sorted(merged.items())
        ]
