import queue
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.enums import BarInterval, MarketSession, RealtimeDataType, RealtimeServiceState
from app.database.models import Instrument, MarketSessionEvent, RealtimeBar, RealtimeQuote, RealtimeTicker
from app.realtime.manager import RealtimeSubscriptionManager
from app.realtime.models import RealtimeBarData, RealtimeQuoteData, RealtimeTickerData
from app.realtime.normalizer import MoomooRealtimeNormalizer, decimal_value
from app.realtime.repository import RealtimeRepository
from app.realtime.session import MarketSessionStateMachine

NY = ZoneInfo("America/New_York")


def add_instrument(db, symbol="US.QQQ", supported=True):
    market, code = symbol.split(".")
    row = Instrument(symbol=symbol, market=market, code=code, is_supported=supported, support_status="SUPPORTED" if supported else "UNSUPPORTED", support_message="可用" if supported else "不支持")
    db.add(row)
    db.commit()
    return row


def quote_row():
    return {"code": "US.QQQ", "data_date": "2026-07-27", "data_time": "09:31:01", "last_price": "500.12", "open_price": "499", "high_price": "501", "low_price": "498", "prev_close_price": "497", "volume": 123, "turnover": "1000.12", "bid_price": "500.11", "ask_price": "500.13", "bid_vol": 2, "ask_vol": 3}


def ticker_row(sequence="10"):
    return {"code": "US.QQQ", "time": "2026-07-27 09:31:02", "price": "500.12", "volume": 5, "turnover": "2500.60", "ticker_direction": "BUY", "sequence": sequence}


def bar_row(closed=True):
    return {"code": "US.QQQ", "time_key": "2026-07-27 09:31:00", "open": "500", "high": "501", "low": "499", "close": "500.5", "volume": 100, "turnover": "50050", "is_closed": closed}


def test_quote_normalization():
    value = MoomooRealtimeNormalizer().quotes([quote_row()])[0]
    assert value.symbol == "US.QQQ" and value.last_price == Decimal("500.12")
    assert value.timestamp_utc.tzinfo and value.timestamp_market.tzinfo and value.timestamp_beijing.tzinfo


def test_ticker_normalization():
    value = MoomooRealtimeNormalizer().tickers([ticker_row()])[0]
    assert value.sequence == "10" and value.volume == 5 and value.price == Decimal("500.12")


def test_ticker_fallback_sequence_is_stable():
    row = ticker_row("")
    one = MoomooRealtimeNormalizer().tickers([row])[0]
    two = MoomooRealtimeNormalizer().tickers([row])[0]
    assert one.sequence == two.sequence and one.sequence


def test_bar_normalization():
    value = MoomooRealtimeNormalizer().bars([bar_row()])[0]
    assert value.interval == BarInterval.MIN_1 and value.is_closed is True


@pytest.mark.parametrize("raw,expected", [("1.10", Decimal("1.10")), (1, Decimal("1")), (None, None), ("nan", None)])
def test_decimal_conversion(raw, expected):
    assert decimal_value(raw) == expected


def test_missing_required_price_rejected():
    row = quote_row()
    row.pop("last_price")
    with pytest.raises(ValueError):
        MoomooRealtimeNormalizer().quotes([row])


def test_quote_upsert(db):
    instrument = add_instrument(db)
    value = MoomooRealtimeNormalizer().quotes([quote_row()])[0]
    repo = RealtimeRepository(db)
    repo.persist([value])
    value.last_price = Decimal("501")
    repo.persist([value])
    rows = db.scalars(select(RealtimeQuote)).all()
    assert len(rows) == 1 and rows[0].last_price == Decimal("501")


def test_ticker_dedup(db):
    add_instrument(db)
    value = MoomooRealtimeNormalizer().tickers([ticker_row()])[0]
    repo = RealtimeRepository(db)
    repo.persist([value, value])
    assert len(db.scalars(select(RealtimeTicker)).all()) == 1


def test_realtime_bar_upsert_and_close(db):
    add_instrument(db)
    normalizer = MoomooRealtimeNormalizer()
    open_bar = normalizer.bars([bar_row(False)])[0]
    repo = RealtimeRepository(db)
    repo.persist([open_bar])
    closed_bar = normalizer.bars([bar_row(True)])[0]
    closed_bar.close = Decimal("502")
    repo.persist([closed_bar])
    rows = db.scalars(select(RealtimeBar)).all()
    assert len(rows) == 1 and rows[0].is_closed and rows[0].close == Decimal("502")


def test_new_minute_closes_previous_bar(db):
    add_instrument(db)
    normalizer = MoomooRealtimeNormalizer()
    first = normalizer.bars([bar_row(False)])[0]
    second = normalizer.bars([bar_row(False)])[0]
    second.timestamp_utc += timedelta(minutes=1)
    second.timestamp_market += timedelta(minutes=1)
    RealtimeRepository(db).persist([first])
    RealtimeRepository(db).persist([second])
    rows = db.scalars(select(RealtimeBar).order_by(RealtimeBar.timestamp_utc)).all()
    assert rows[0].is_closed is True and rows[1].is_closed is False


@pytest.mark.parametrize(
    "hour,minute,expected",
    [(8, 0, MarketSession.PRE_MARKET), (10, 0, MarketSession.REGULAR), (17, 0, MarketSession.AFTER_HOURS), (22, 0, MarketSession.OVERNIGHT)],
)
def test_session_time_windows(hour, minute, expected):
    value = datetime(2026, 7, 27, hour, minute, tzinfo=NY)
    assert MarketSessionStateMachine().update(value).session == expected


def test_weekend_closed():
    assert MarketSessionStateMachine().update(datetime(2026, 8, 1, 10, tzinfo=NY)).session == MarketSession.CLOSED


def test_moomoo_state_has_priority():
    value = datetime(2026, 7, 27, 10, tzinfo=NY)
    result = MarketSessionStateMachine().update(value, "AFTER_HOURS")
    assert result.session == MarketSession.AFTER_HOURS and result.source == "MOOMOO_MARKET_STATE"


def test_naive_time_is_unknown():
    assert MarketSessionStateMachine().update(datetime(2026, 7, 27, 10)).session == MarketSession.UNKNOWN


class FakeProvider:
    def __init__(self, callback, fail_symbols=None, connect_error=False):
        self.callback = callback
        self.fail_symbols = set(fail_symbols or [])
        self.connect_error = connect_error
        self.connected = False
        self.closed = False
        self.handlers_registered = False
        self.subscribe_calls = []

    def connect(self):
        if self.connect_error:
            raise ConnectionError("断线")
        self.connected = True
        self.handlers_registered = True

    def subscribe(self, symbols, types):
        self.subscribe_calls.append((tuple(symbols), frozenset(types)))
        return {symbol + ":" + item.value: "失败" for symbol in symbols for item in types if symbol in self.fail_symbols}

    def unsubscribe(self, symbols, types):
        return {}

    def close(self):
        self.closed = True
        self.connected = False


def manager_for(db, provider_builder=None, capacity=10, batch_size=2, reconnects=2):
    add_instrument(db, "US.QQQ")
    add_instrument(db, "US.SOXL")
    factory = db.get_bind()
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=factory, expire_on_commit=False)
    builder = provider_builder or (lambda callback: FakeProvider(callback))
    return RealtimeSubscriptionManager(builder, ["US.QQQ", "US.SOXL"], [RealtimeDataType.QUOTE], queue_capacity=capacity, batch_size=batch_size, flush_interval=0.02, max_reconnect_attempts=reconnects, reconnect_delay=0, session_factory=session_factory)


def test_subscribe_and_unsubscribe_idempotent(db):
    manager = manager_for(db)
    first = manager.start()
    second = manager.subscribe_symbols(["US.QQQ"], [RealtimeDataType.QUOTE])
    assert "US.QQQ" in first.successful and "US.QQQ" in second.skipped
    manager.unsubscribe_symbols(["US.QQQ"], [RealtimeDataType.QUOTE])
    result = manager.unsubscribe_symbols(["US.QQQ"], [RealtimeDataType.QUOTE])
    assert "US.QQQ" in result.skipped
    manager.stop()


def test_single_symbol_failure_isolated(db):
    manager = manager_for(db, lambda callback: FakeProvider(callback, {"US.SOXL"}))
    result = manager.start()
    assert "US.QQQ" in result.successful and "US.SOXL" in result.failed
    manager.stop()


def test_context_closes_and_writer_stops(db):
    manager = manager_for(db)
    manager.start()
    provider = manager.provider
    writer = manager.writer_thread
    manager.stop()
    assert provider.closed and not writer.is_alive()


def test_duplicate_start_has_one_thread_and_context(db):
    created = []
    def build(callback):
        value = FakeProvider(callback)
        created.append(value)
        return value
    manager = manager_for(db, build)
    manager.start()
    writer = manager.writer_thread
    manager.start()
    assert len(created) == 1 and manager.writer_thread is writer
    manager.stop()


def test_queue_capacity_and_drop_count(db):
    manager = manager_for(db, capacity=1)
    manager.enqueue(object())
    manager.enqueue(object())
    assert manager.queue.qsize() == 1 and manager.dropped_count == 1


def test_duplicate_callback_is_counted(db):
    manager = manager_for(db)
    value = MoomooRealtimeNormalizer().tickers([ticker_row()])[0]
    manager.enqueue(value)
    manager.enqueue(value)
    assert manager.duplicate_count == 1


def test_batch_flush_and_stop_flushes_remaining(db):
    manager = manager_for(db, batch_size=10)
    manager.start()
    manager.enqueue(MoomooRealtimeNormalizer().quotes([quote_row()])[0])
    manager.stop()
    assert manager.persisted_count == 1 and manager.queue.empty()


def test_reconnect_restores_subscription(db):
    providers = []
    def build(callback):
        item = FakeProvider(callback)
        providers.append(item)
        return item
    manager = manager_for(db, build)
    manager.start()
    assert manager.reconnect("测试断线")
    assert len(providers) == 2 and "US.QQQ" in manager.subscriptions
    manager.stop()


def test_reconnect_max_attempts(db):
    calls = {"count": 0}
    def build(callback):
        calls["count"] += 1
        return FakeProvider(callback, connect_error=calls["count"] > 1)
    manager = manager_for(db, build, reconnects=2)
    manager.start()
    assert not manager.reconnect("持续断线")
    assert manager.status == RealtimeServiceState.FAILED and manager.reconnect_count == 2
    manager.stop()


def test_health_connected_and_degraded(db):
    manager = manager_for(db)
    manager.start()
    assert manager.get_status().status == "CONNECTED"
    manager.dropped_count = 1
    manager.status = RealtimeServiceState.DEGRADED
    assert manager.get_status().warnings
    manager.stop()


def test_stale_liquid_symbol_detection(db):
    manager = manager_for(db)
    manager.start()
    manager.last_message_at = datetime.now(timezone.utc) - timedelta(hours=1)
    assert manager.check_stale()
    manager.stop()


def test_low_liquidity_does_not_mark_global_stale(db):
    manager = manager_for(db)
    manager.start()
    manager.subscriptions = {"US.SOXL": {RealtimeDataType.TICKER}}
    manager.last_message_at = datetime.now(timezone.utc) - timedelta(hours=1)
    assert not manager.check_stale()
    manager.stop()


def test_valid_symbols_filter(db):
    add_instrument(db, "US.QQQ")
    add_instrument(db, "US.VIX", supported=False)
    valid, invalid = RealtimeRepository(db).valid_symbols(["US.QQQ", "US.VIX", "US.NONE"])
    assert valid == ["US.QQQ"] and set(invalid) == {"US.VIX", "US.NONE"}


def test_cleanup_is_dry_run_by_default(db):
    add_instrument(db)
    value = MoomooRealtimeNormalizer().tickers([ticker_row()])[0]
    value.ticker_time_utc = datetime.now(timezone.utc) - timedelta(days=31)
    RealtimeRepository(db).persist([value])
    counts = RealtimeRepository(db).cleanup_counts(30, 90, 365)
    assert counts["realtime_tickers"] == 1 and db.scalar(select(RealtimeTicker.id)) is not None


def test_session_event_recording(db):
    RealtimeRepository(db).record_session_event("PRE_MARKET", "REGULAR", "TIME_INFERENCE", "开盘", datetime.now(timezone.utc))
    assert db.scalar(select(MarketSessionEvent.current_session)) == "REGULAR"


def test_overnight_is_marked_as_inference():
    result = MarketSessionStateMachine().update(datetime(2026, 7, 27, 22, tzinfo=NY))
    assert result.session == MarketSession.OVERNIGHT
    assert result.source == "TIME_INFERENCE" and result.confidence == "MEDIUM"
    assert "未声明可交易" in result.reason


def test_session_next_transition_is_timezone_aware():
    result = MarketSessionStateMachine().update(datetime(2026, 7, 27, 8, tzinfo=NY))
    assert result.next_expected_transition is not None
    assert result.next_expected_transition.tzinfo is not None


def test_manager_has_requested_types(db):
    manager = manager_for(db)
    assert manager.requested_types == {RealtimeDataType.QUOTE}


def test_status_persists_without_sensitive_fields(db):
    manager = manager_for(db)
    manager.start()
    manager.stop()
    row = RealtimeRepository(db).status()
    assert row.status == "STOPPED"
    assert "account" not in str(row.metadata_json).lower()


def test_cleanup_apply_removes_expired_ticker(db):
    add_instrument(db)
    value = MoomooRealtimeNormalizer().tickers([ticker_row()])[0]
    value.ticker_time_utc = datetime.now(timezone.utc) - timedelta(days=31)
    RealtimeRepository(db).persist([value])
    RealtimeRepository(db).cleanup_counts(30, 90, 365, apply=True)
    assert db.scalar(select(RealtimeTicker.id)) is None


def test_configured_symbol_deduplication(monkeypatch):
    from app.core.config import Settings
    settings = Settings(realtime_symbols="US.QQQ,us.qqq, US.SOXL")
    assert settings.realtime_symbol_list() == ["US.QQQ", "US.SOXL"]


def test_invalid_symbol_does_not_start_subscription(db):
    manager = manager_for(db)
    manager.requested_symbols.append("US.NONE")
    result = manager.start()
    assert "US.NONE" in result.failed and manager.status == RealtimeServiceState.CONNECTED
    manager.stop()
