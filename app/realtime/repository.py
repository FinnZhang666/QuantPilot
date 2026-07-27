import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database.models import (
    Instrument,
    MarketSessionEvent,
    RealtimeBar,
    RealtimeQuote,
    RealtimeServiceStatus,
    RealtimeTicker,
    SystemEvent,
)
from app.realtime.models import RealtimeBarData, RealtimeQuoteData, RealtimeTickerData


class RealtimeRepository:
    def __init__(self, db: Session, lock_retries: int = 3, retry_delay: float = 0.1):
        self.db = db
        self.lock_retries = lock_retries
        self.retry_delay = retry_delay

    def valid_symbols(self, symbols: Iterable[str]) -> Tuple[List[str], Dict[str, str]]:
        requested = list(dict.fromkeys(value.upper() for value in symbols))
        rows = self.db.scalars(select(Instrument).where(Instrument.symbol.in_(requested))).all()
        found = {row.symbol: row for row in rows}
        valid, invalid = [], {}
        for symbol in requested:
            row = found.get(symbol)
            if row is None:
                invalid[symbol] = "标的不在instruments表"
            elif not row.is_active:
                invalid[symbol] = "标的未启用"
            elif not row.is_supported:
                invalid[symbol] = row.support_message or "标的不支持"
            else:
                valid.append(symbol)
        return valid, invalid

    def persist(self, items: List[Any]) -> Tuple[int, int]:
        by_type: Dict[type, List[Any]] = {}
        for item in items:
            by_type.setdefault(type(item), []).append(item)
        inserted = duplicate = 0
        for item_type, values in by_type.items():
            if item_type is RealtimeQuoteData:
                count = self._upsert_quotes(values)
            elif item_type is RealtimeTickerData:
                count = self._upsert_tickers(values)
            elif item_type is RealtimeBarData:
                count = self._upsert_bars(values)
            else:
                continue
            inserted += count
            duplicate += len(values) - count
        return inserted, duplicate

    def _instrument_ids(self, symbols: Iterable[str]) -> Dict[str, int]:
        rows = self.db.execute(select(Instrument.symbol, Instrument.id).where(Instrument.symbol.in_(set(symbols))))
        return dict(rows.all())

    def _execute_with_retry(self, statements: List[Any]) -> None:
        for attempt in range(self.lock_retries + 1):
            try:
                for statement in statements:
                    self.db.execute(statement)
                self.db.commit()
                return
            except OperationalError as exc:
                self.db.rollback()
                if "locked" not in str(exc).lower() or attempt >= self.lock_retries:
                    self._record_error(type(exc).__name__)
                    raise
                time.sleep(self.retry_delay * (attempt + 1))

    def _upsert_quotes(self, rows: List[RealtimeQuoteData]) -> int:
        ids = self._instrument_ids(row.symbol for row in rows)
        values = [{
            "instrument_id": ids[row.symbol], "symbol": row.symbol,
            "timestamp_utc": row.timestamp_utc, "timestamp_market": row.timestamp_market,
            "timestamp_beijing": row.timestamp_beijing, "last_price": row.last_price,
            "open_price": row.open_price, "high_price": row.high_price, "low_price": row.low_price,
            "prev_close": row.prev_close, "volume": row.volume, "turnover": row.turnover,
            "amplitude": row.amplitude, "turnover_rate": row.turnover_rate,
            "bid_price": row.bid_price, "ask_price": row.ask_price,
            "bid_volume": row.bid_volume, "ask_volume": row.ask_volume,
            "market_session": row.market_session.value, "market_status": row.market_status,
            "data_source": row.data_source, "received_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        } for row in rows if row.symbol in ids]
        statements = []
        for batch in self._batches(values):
            stmt = sqlite_insert(RealtimeQuote).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "timestamp_utc", "data_source"],
                set_={key: getattr(stmt.excluded, key) for key in values[0] if key not in {"instrument_id", "symbol", "timestamp_utc", "data_source", "created_at"}},
            )
            statements.append(stmt)
        self._execute_with_retry(statements)
        return len(values)

    def _upsert_tickers(self, rows: List[RealtimeTickerData]) -> int:
        ids = self._instrument_ids(row.symbol for row in rows)
        values = [{
            "instrument_id": ids[row.symbol], "symbol": row.symbol,
            "ticker_time_utc": row.ticker_time_utc, "ticker_time_market": row.ticker_time_market,
            "price": row.price, "volume": row.volume, "turnover": row.turnover,
            "direction": row.direction, "sequence": row.sequence,
            "market_session": row.market_session.value, "data_source": row.data_source,
            "created_at": datetime.now(timezone.utc),
        } for row in rows if row.symbol in ids]
        unique_values = {}
        for value in values:
            key = (value["symbol"], value["sequence"], value["ticker_time_utc"], value["data_source"])
            unique_values[key] = value
        values = list(unique_values.values())
        statements = []
        for batch in self._batches(values):
            stmt = sqlite_insert(RealtimeTicker).values(batch).on_conflict_do_nothing(
                index_elements=["symbol", "sequence", "ticker_time_utc", "data_source"]
            )
            statements.append(stmt)
        self._execute_with_retry(statements)
        return len(values)

    def _upsert_bars(self, rows: List[RealtimeBarData]) -> int:
        ids = self._instrument_ids(row.symbol for row in rows)
        values = [{
            "instrument_id": ids[row.symbol], "symbol": row.symbol, "interval": row.interval.value,
            "timestamp_utc": row.timestamp_utc, "timestamp_market": row.timestamp_market,
            "trading_date": row.trading_date, "open": row.open, "high": row.high,
            "low": row.low, "close": row.close, "volume": row.volume, "turnover": row.turnover,
            "is_closed": row.is_closed, "market_session": row.market_session.value,
            "data_source": row.data_source, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        } for row in rows if row.symbol in ids]
        latest_by_symbol: Dict[str, datetime] = {}
        for value in values:
            current = latest_by_symbol.get(value["symbol"])
            if current is None or value["timestamp_utc"] > current:
                latest_by_symbol[value["symbol"]] = value["timestamp_utc"]
        statements = [
            update(RealtimeBar).where(
                RealtimeBar.symbol == symbol,
                RealtimeBar.timestamp_utc < latest,
                RealtimeBar.is_closed.is_(False),
            ).values(is_closed=True, updated_at=datetime.now(timezone.utc))
            for symbol, latest in latest_by_symbol.items()
        ]
        for batch in self._batches(values):
            stmt = sqlite_insert(RealtimeBar).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "interval", "timestamp_utc", "data_source"],
                set_={key: getattr(stmt.excluded, key) for key in values[0] if key not in {"instrument_id", "symbol", "interval", "timestamp_utc", "data_source", "created_at"}},
            )
            statements.append(stmt)
        self._execute_with_retry(statements)
        return len(values)

    @staticmethod
    def _batches(values: List[Dict[str, Any]], size: int = 200) -> Iterable[List[Dict[str, Any]]]:
        for index in range(0, len(values), size):
            yield values[index:index + size]

    def status(self) -> RealtimeServiceStatus:
        row = self.db.scalar(select(RealtimeServiceStatus).where(RealtimeServiceStatus.service_name == "moomoo_realtime"))
        if row is None:
            row = RealtimeServiceStatus(service_name="moomoo_realtime", status="STOPPED")
            self.db.add(row)
            self.db.commit()
        return row

    def save_status(self, **values: Any) -> RealtimeServiceStatus:
        row = self.status()
        for key, value in values.items():
            setattr(row, key, value)
        self.db.commit()
        return row

    def record_session_event(self, previous: str, current: str, source: str, reason: str, at: datetime) -> None:
        self.db.add(MarketSessionEvent(
            previous_session=previous, current_session=current, source_status=source,
            event_time_utc=at.astimezone(timezone.utc), event_time_market=at,
            reason=reason,
        ))
        self.db.commit()

    def _record_error(self, name: str) -> None:
        try:
            self.db.add(SystemEvent(level="ERROR", component="realtime", event_type="DATABASE_WRITE_FAILED", message="实时行情批量写入失败", payload_json={"error": name}))
            self.db.commit()
        except Exception:
            self.db.rollback()

    def cleanup_counts(self, ticker_days: int, quote_days: int, bar_days: int, apply: bool = False) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        specs = [
            ("realtime_tickers", RealtimeTicker, RealtimeTicker.ticker_time_utc, ticker_days),
            ("realtime_quotes", RealtimeQuote, RealtimeQuote.timestamp_utc, quote_days),
            ("realtime_bars", RealtimeBar, RealtimeBar.timestamp_utc, bar_days),
        ]
        result = {}
        for name, model, column, days in specs:
            ids = self.db.scalars(select(model.id).where(column < now - timedelta(days=days))).all()
            result[name] = len(ids)
            if apply and ids:
                self.db.execute(delete(model).where(model.id.in_(ids)))
        if apply:
            self.db.commit()
        return result
