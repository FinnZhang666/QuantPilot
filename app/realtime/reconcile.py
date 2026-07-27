from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database.models import MarketBar, RealtimeBar


class RealtimeHistoryReconciler:
    def __init__(self, db: Session):
        self.db = db

    def compare_range(self, symbol: str, trading_date: date) -> Dict[str, Any]:
        realtime = self.db.scalars(select(RealtimeBar).where(
            RealtimeBar.symbol == symbol.upper(),
            RealtimeBar.trading_date == trading_date.isoformat(),
            RealtimeBar.is_closed.is_(True),
        )).all()
        history = self.db.scalars(select(MarketBar).where(
            MarketBar.symbol == symbol.upper(),
            MarketBar.interval == "1m",
            MarketBar.trading_date == trading_date.isoformat(),
        )).all()
        rmap = {self._key(row.timestamp_utc): row for row in realtime}
        hmap = {self._key(row.timestamp_utc): row for row in history}
        differences: List[Dict[str, Any]] = []
        for key in sorted(set(rmap) | set(hmap)):
            rrow, hrow = rmap.get(key), hmap.get(key)
            if rrow is None:
                differences.append({"timestamp": key, "type": "实时缺失"})
            elif hrow is None:
                differences.append({"timestamp": key, "type": "历史缺失"})
            else:
                price_fields = [name for name in ("open", "high", "low", "close") if Decimal(str(getattr(rrow, name))) != Decimal(str(getattr(hrow, name)))]
                if price_fields:
                    differences.append({"timestamp": key, "type": "价格差异", "fields": price_fields})
                if rrow.volume != hrow.volume:
                    differences.append({"timestamp": key, "type": "成交量差异", "realtime": rrow.volume, "history": hrow.volume})
                if rrow.market_session != hrow.market_session:
                    differences.append({"timestamp": key, "type": "时段差异", "realtime": rrow.market_session, "history": hrow.market_session})
        return {"symbol": symbol.upper(), "date": trading_date.isoformat(), "realtime_count": len(realtime), "history_count": len(history), "differences": differences}

    def promote_closed_bars(self, symbol: str, trading_date: date) -> int:
        rows = self.db.scalars(select(RealtimeBar).where(
            RealtimeBar.symbol == symbol.upper(),
            RealtimeBar.trading_date == trading_date.isoformat(),
            RealtimeBar.is_closed.is_(True),
        )).all()
        count = 0
        for row in rows:
            statement = sqlite_insert(MarketBar).values(
                instrument_id=row.instrument_id, symbol=row.symbol, interval="1m",
                timestamp_utc=row.timestamp_utc, timestamp_market=row.timestamp_market,
                trading_date=row.trading_date, open=row.open, high=row.high, low=row.low,
                close=row.close, volume=row.volume, turnover=row.turnover,
                is_blank=False, market_session=row.market_session,
                adjustment_type="NONE", data_source="MOOMOO_REALTIME",
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                index_elements=["symbol", "interval", "timestamp_utc", "adjustment_type", "data_source"],
                set_={"open": row.open, "high": row.high, "low": row.low, "close": row.close, "volume": row.volume, "turnover": row.turnover, "market_session": row.market_session, "updated_at": datetime.now(timezone.utc)},
            )
            self.db.execute(statement)
            count += 1
        self.db.commit()
        return count

    @staticmethod
    def _key(value: datetime) -> str:
        source = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return source.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
