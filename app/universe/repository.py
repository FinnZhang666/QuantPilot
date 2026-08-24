from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.database.models import UniverseInstrument, UniverseMembership, UniverseUpdateRun
from app.universe.models import HoldingRecord, UniverseSource


class UniverseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_run(self, sources):
        row = UniverseUpdateRun(status="RUNNING", sources_json=sources, summary_json={})
        self.db.add(row)
        self.db.commit()
        return row

    def sync_source(self, source: UniverseSource, records: Iterable[HoldingRecord]):
        now = datetime.now(timezone.utc)
        before = set(self.db.scalars(select(UniverseInstrument.symbol).join(
            UniverseMembership, UniverseMembership.universe_id == UniverseInstrument.id,
        ).where(UniverseMembership.fund_symbol == source.fund_symbol,
                UniverseMembership.is_active.is_(True))))
        seen = set()
        added = reactivated = 0
        for record in records:
            seen.add(record.symbol)
            item = self.db.scalar(select(UniverseInstrument).where(
                UniverseInstrument.market == "US", UniverseInstrument.symbol == record.symbol,
            ))
            if item is None:
                item = UniverseInstrument(
                    symbol=record.symbol, market="US", company_name=record.company_name,
                    sector=record.sector, industry=record.industry, market_cap=record.market_cap,
                    first_seen=now, last_update=now, status="ACTIVE",
                )
                self.db.add(item)
                self.db.flush()
                added += 1
            else:
                if item.status != "ACTIVE":
                    reactivated += 1
                item.status = "ACTIVE"
                item.last_update = now
                for name in ("company_name", "sector", "industry", "market_cap"):
                    value = getattr(record, name)
                    if value is not None and value != "":
                        setattr(item, name, value)
            membership = self.db.scalar(select(UniverseMembership).where(
                UniverseMembership.universe_id == item.id,
                UniverseMembership.fund_symbol == source.fund_symbol,
            ))
            if membership is None:
                membership = UniverseMembership(
                    universe_id=item.id, fund_symbol=source.fund_symbol,
                    first_seen=now, last_seen=now, source_name=source.provider,
                )
                self.db.add(membership)
            membership.weight = record.weight
            membership.is_active = True
            membership.last_seen = now
            membership.source_name = source.provider
            membership.source_url = source.url
        removed_symbols = before - seen
        if removed_symbols:
            rows = self.db.scalars(select(UniverseMembership).join(
                UniverseInstrument, UniverseInstrument.id == UniverseMembership.universe_id,
            ).where(UniverseMembership.fund_symbol == source.fund_symbol,
                    UniverseInstrument.symbol.in_(removed_symbols))).all()
            for membership in rows:
                membership.is_active = False
        self.db.flush()
        affected = before | seen
        for symbol in affected:
            item = self.db.scalar(select(UniverseInstrument).where(
                UniverseInstrument.market == "US", UniverseInstrument.symbol == symbol,
            ))
            if item is None:
                continue
            active = self.db.scalar(select(func.count()).select_from(UniverseMembership).where(
                UniverseMembership.universe_id == item.id,
                UniverseMembership.is_active.is_(True),
            )) or 0
            item.status = "ACTIVE" if active else "INACTIVE"
            item.last_update = now
        self.db.commit()
        return {"added": added, "reactivated": reactivated, "inactivated": len(removed_symbols)}

    def finish_run(self, run, status, summary):
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.added_count = summary.get("added", 0)
        run.reactivated_count = summary.get("reactivated", 0)
        run.inactivated_count = summary.get("inactivated", 0)
        run.active_count = self.db.scalar(select(func.count()).select_from(UniverseInstrument).where(
            UniverseInstrument.status == "ACTIVE")) or 0
        run.error_count = len(summary.get("errors", []))
        run.summary_json = summary
        self.db.commit()
        return run

    def get(self, symbol: str, market="US"):
        return self.db.scalar(select(UniverseInstrument).where(
            UniverseInstrument.market == market, UniverseInstrument.symbol == symbol,
        ))

    def list(self, search=None, fund=None, sector=None, industry=None, status=None,
             sort="symbol", direction="asc", limit=100, offset=0):
        filters = []
        if search:
            term = "%" + search.strip() + "%"
            filters.append(or_(UniverseInstrument.symbol.ilike(term), UniverseInstrument.company_name.ilike(term)))
        if sector:
            filters.append(UniverseInstrument.sector == sector)
        if industry:
            filters.append(UniverseInstrument.industry == industry)
        if status:
            filters.append(UniverseInstrument.status == status.upper())
        if fund:
            funds = [value.strip().upper() for value in fund.split("+") if value.strip()]
            for value in funds:
                filters.append(exists(select(UniverseMembership.id).where(
                    UniverseMembership.universe_id == UniverseInstrument.id,
                    UniverseMembership.fund_symbol == value,
                    UniverseMembership.is_active.is_(True),
                )))
        sortable = {
            "symbol": UniverseInstrument.symbol, "company_name": UniverseInstrument.company_name,
            "sector": UniverseInstrument.sector, "industry": UniverseInstrument.industry,
            "last_update": UniverseInstrument.last_update, "market_cap": UniverseInstrument.market_cap,
        }
        column = sortable.get(sort, UniverseInstrument.symbol)
        order = column.desc() if direction.lower() == "desc" else column.asc()
        total = self.db.scalar(select(func.count()).select_from(UniverseInstrument).where(*filters)) or 0
        rows = self.db.scalars(select(UniverseInstrument).where(*filters).order_by(order, UniverseInstrument.symbol).offset(offset).limit(limit)).all()
        return rows, total

    def memberships(self, universe_ids) -> Dict[int, list]:
        result = {value: [] for value in universe_ids}
        if not result:
            return result
        for row in self.db.scalars(select(UniverseMembership).where(
            UniverseMembership.universe_id.in_(result),
        ).order_by(UniverseMembership.fund_symbol)):
            result[row.universe_id].append(row)
        return result

    def latest_success_at(self):
        return self.db.scalar(select(UniverseUpdateRun.completed_at).where(
            UniverseUpdateRun.status.in_(("SUCCESS", "PARTIAL_SUCCESS")),
        ).order_by(UniverseUpdateRun.completed_at.desc()).limit(1))
