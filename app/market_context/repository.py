from sqlalchemy import desc, func, select

from app.database.models import (
    MarketBar, MarketContextSnapshot, SectorContextSnapshot, UniverseInstrument,
)


class MarketContextRepository:
    def __init__(self, db):
        self.db = db

    def closes(self, symbol, at, limit=80):
        bare = symbol.upper().removeprefix("US.")
        rows = list(self.db.scalars(select(MarketBar).where(
            MarketBar.symbol.in_((bare, "US." + bare)), MarketBar.interval == "1d",
            MarketBar.timestamp_utc <= at, MarketBar.is_blank.is_(False),
        ).order_by(desc(MarketBar.timestamp_utc)).limit(limit)))
        return [float(row.close) for row in reversed(rows)], (rows[0].timestamp_utc if rows else None)

    def breadth(self, sector, at):
        symbols = list(self.db.scalars(select(UniverseInstrument.symbol).where(
            UniverseInstrument.sector == sector, UniverseInstrument.status == "ACTIVE")))
        positive = total = 0
        for symbol in symbols:
            closes, _ = self.closes(symbol, at, limit=2)
            if len(closes) >= 2:
                total += 1
                positive += closes[-1] > closes[-2]
        return (positive / total if total else None), total

    def latest_global(self, at=None):
        query = select(MarketContextSnapshot)
        if at is not None: query = query.where(MarketContextSnapshot.timestamp <= at)
        return self.db.scalar(query.order_by(desc(MarketContextSnapshot.timestamp)).limit(1))

    def latest_sector(self, sector, at=None):
        query = select(SectorContextSnapshot).where(SectorContextSnapshot.sector_code == sector)
        if at is not None: query = query.where(SectorContextSnapshot.timestamp <= at)
        return self.db.scalar(query.order_by(desc(SectorContextSnapshot.timestamp)).limit(1))

    def sectors(self):
        return list(self.db.scalars(select(UniverseInstrument.sector).where(
            UniverseInstrument.status == "ACTIVE", UniverseInstrument.sector.is_not(None),
        ).distinct().order_by(UniverseInstrument.sector)))

    def instrument(self, symbol):
        return self.db.scalar(select(UniverseInstrument).where(
            UniverseInstrument.symbol == symbol.upper().removeprefix("US.")))

    def save_global(self, row):
        existing = self.db.scalar(select(MarketContextSnapshot).where(
            MarketContextSnapshot.timestamp == row.timestamp,
            MarketContextSnapshot.session == row.session,
            MarketContextSnapshot.model_version == row.model_version))
        if existing: return existing, False
        self.db.add(row); self.db.flush(); return row, True

    def save_sector(self, row):
        existing = self.db.scalar(select(SectorContextSnapshot).where(
            SectorContextSnapshot.timestamp == row.timestamp,
            SectorContextSnapshot.sector_code == row.sector_code,
            SectorContextSnapshot.model_version == row.model_version))
        if existing: return existing, False
        self.db.add(row); self.db.flush(); return row, True

    def historical_global(self, start=None, end=None):
        query = select(MarketContextSnapshot)
        if start: query = query.where(MarketContextSnapshot.timestamp >= start)
        if end: query = query.where(MarketContextSnapshot.timestamp <= end)
        return list(self.db.scalars(query.order_by(MarketContextSnapshot.timestamp)))

    def historical_sector(self, sector, start=None, end=None):
        query = select(SectorContextSnapshot).where(SectorContextSnapshot.sector_code == sector)
        if start: query = query.where(SectorContextSnapshot.timestamp >= start)
        if end: query = query.where(SectorContextSnapshot.timestamp <= end)
        return list(self.db.scalars(query.order_by(SectorContextSnapshot.timestamp)))
