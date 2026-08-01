from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.enums import AdjustmentType, BarInterval, HistoryErrorCode, MarketSession
from app.data.providers.moomoo import MoomooConnectionManager
from app.database.models import HistoryDataIssue, Instrument, MarketBar
from app.historical.instruments import InstrumentService
from app.historical.models import HistoryFetchResult, MarketBarData
from app.historical.moomoo_provider import (
    MoomooHistoricalDataProvider,
    classify_sdk_error,
)
from app.historical.sync_service import HistoricalDataSyncService
from app.historical.timezone import NEW_YORK, SHANGHAI, classify_us_session, market_time_to_utc


class FakeSocket:
    def close(self):
        pass


def reachable(*args, **kwargs):
    return FakeSocket()


class Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orientation):
        return self.rows


class Quote:
    def __init__(self, responses):
        self.responses = list(responses)
        self.closed = False
        self.calls = 0

    def request_history_kline(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)

    def close(self):
        self.closed = True


class EnumValues:
    K_1M = "K_1M"
    K_5M = "K_5M"
    K_15M = "K_15M"
    K_30M = "K_30M"
    K_60M = "K_60M"
    K_DAY = "K_DAY"


class AdjustValues:
    NONE = "NONE"
    QFQ = "QFQ"
    HFQ = "HFQ"


class FakeSdk:
    RET_OK = 0
    KLType = EnumValues
    AuType = AdjustValues

    class Session:
        ALL = "ALL"

    def __init__(self, quote):
        self.quote = quote

    def OpenQuoteContext(self, **kwargs):
        return self.quote


def raw_bar(close="101"):
    return {
        "time_key": "2026-07-24 09:30:00",
        "open": "100",
        "high": "102",
        "low": "99",
        "close": close,
        "volume": 1000,
        "turnover": "100500.25",
        "change_rate": "1.2",
        "last_close": "99.8",
    }


def make_provider(responses, max_pages=500):
    quote = Quote(responses)
    sdk = FakeSdk(quote)
    manager = MoomooConnectionManager(sdk_loader=lambda: sdk, socket_connector=reachable)
    provider = MoomooHistoricalDataProvider(
        manager, max_retries=0, request_interval_seconds=0, max_pages=max_pages, sleep=lambda _: None
    )
    return provider, quote, sdk


@pytest.mark.parametrize("interval", list(BarInterval))
def test_bar_interval_mapping(interval):
    provider, _, sdk = make_provider([])
    assert provider.interval_map(sdk)[interval]


@pytest.mark.parametrize("adjustment", list(AdjustmentType))
def test_adjustment_mapping(adjustment):
    provider, _, sdk = make_provider([])
    assert provider.adjustment_map(sdk)[adjustment]


def test_dataframe_normalization_uses_decimal():
    provider, _, _ = make_provider([])
    bar = provider.normalize_rows(
        Frame([raw_bar()]), "US.QQQ", BarInterval.MIN_1, AdjustmentType.FORWARD
    )[0]
    assert bar.close == Decimal("101")
    assert bar.turnover == Decimal("100500.25")


def test_timezone_conversions():
    utc = market_time_to_utc("2026-07-24 09:30:00")
    assert utc.hour == 13
    assert utc.astimezone(NEW_YORK).hour == 9
    assert utc.astimezone(SHANGHAI).hour == 21


def test_daylight_saving_conversion():
    summer = market_time_to_utc("2026-07-24 09:30:00")
    winter = market_time_to_utc("2026-01-24 09:30:00")
    assert summer.hour == 13
    assert winter.hour == 14


def market_bar(**overrides):
    values = dict(
        symbol="US.QQQ",
        interval=BarInterval.DAY_1,
        timestamp_utc=datetime(2026, 7, 24, 13, 30, tzinfo=timezone.utc),
        timestamp_market=datetime(2026, 7, 24, 9, 30, tzinfo=NEW_YORK),
        trading_date=datetime(2026, 7, 24).date(),
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=100,
        turnover=Decimal("10000"),
        change_rate=Decimal("1"),
        last_close=Decimal("100"),
        is_blank=False,
        market_session=MarketSession.REGULAR,
        adjustment_type=AdjustmentType.FORWARD,
    )
    values.update(overrides)
    return MarketBarData(**values)


def test_valid_ohlc():
    assert market_bar().validation_errors() == []


def test_invalid_ohlc_is_rejected():
    assert "OHLC关系无效" in market_bar(high=Decimal("100")).validation_errors()


def test_negative_volume_is_rejected():
    assert "成交量不能为负数" in market_bar(volume=-1).validation_errors()


@pytest.mark.parametrize(
    "hour,expected",
    [(2, MarketSession.OVERNIGHT), (8, MarketSession.PRE_MARKET), (10, MarketSession.REGULAR), (18, MarketSession.AFTER_HOURS)],
)
def test_market_session_classification(hour, expected):
    value = datetime(2026, 7, 24, hour, 0, tzinfo=NEW_YORK)
    assert classify_us_session(value) == expected


def supported_instrument(db):
    row = Instrument(
        symbol="US.QQQ", market="US", code="QQQ", alias="QQQ", display_name="QQQ",
        is_supported=True, support_status="SUPPORTED", support_message="可用"
    )
    db.add(row)
    db.commit()
    return row


class StaticProvider:
    def __init__(self, bars=None, error=None):
        self.bars = bars or []
        self.error = error

    def fetch_bars(self, symbol, interval, start, end, adjustment):
        return HistoryFetchResult(
            symbol=symbol, interval=interval, bars=self.bars,
            error_code=self.error,
            error_message_zh="模拟失败" if self.error else "",
            pages_requested=1,
        )


def test_instrument_unique_constraint(db):
    db.add(Instrument(symbol="US.A", market="US", code="A"))
    db.commit()
    db.add(Instrument(symbol="US.A2", market="US", code="A"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_instrument_alias_mapping(db):
    InstrumentService(db).initialize_defaults()
    assert InstrumentService(db).resolve("QQQ").symbol == "US.QQQ"


def test_duplicate_bar_is_upserted_not_duplicated(db):
    supported_instrument(db)
    bar = market_bar()
    service = HistoricalDataSyncService(db, StaticProvider([bar]))
    start = bar.timestamp_utc - timedelta(days=1)
    end = bar.timestamp_utc + timedelta(days=1)
    first = service.sync_symbol("US.QQQ", BarInterval.DAY_1, start, end)
    second = service.sync_symbol("US.QQQ", BarInterval.DAY_1, start, end)
    assert first.rows_inserted == 1
    assert second.rows_updated == 1
    assert db.scalar(select(func.count(MarketBar.id))) == 1


def test_large_bar_batch_is_chunked_for_sqlite(db):
    supported_instrument(db)
    base = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    bars = [
        market_bar(
            interval=BarInterval.MIN_15,
            timestamp_utc=base + timedelta(minutes=15 * index),
            timestamp_market=(base + timedelta(minutes=15 * index)).astimezone(NEW_YORK),
            trading_date=(base + timedelta(minutes=15 * index)).astimezone(NEW_YORK).date(),
        )
        for index in range(1200)
    ]
    service = HistoricalDataSyncService(db, StaticProvider(bars))
    start, end = base - timedelta(days=1), base + timedelta(days=20)

    first = service.sync_symbol("US.QQQ", BarInterval.MIN_15, start, end)
    second = service.sync_symbol("US.QQQ", BarInterval.MIN_15, start, end)

    assert first.rows_inserted == 1200
    assert second.rows_updated == 1200
    assert db.scalar(select(func.count(MarketBar.id))) == 1200


def test_bar_upsert_updates_values(db):
    supported_instrument(db)
    first = market_bar(close=Decimal("101"))
    second = market_bar(close=Decimal("101.5"))
    start, end = first.timestamp_utc - timedelta(days=1), first.timestamp_utc + timedelta(days=1)
    HistoricalDataSyncService(db, StaticProvider([first])).sync_symbol("US.QQQ", BarInterval.DAY_1, start, end)
    HistoricalDataSyncService(db, StaticProvider([second])).sync_symbol("US.QQQ", BarInterval.DAY_1, start, end)
    assert db.scalar(select(MarketBar.close)) == Decimal("101.50000000")


def test_incremental_start_uses_latest_bar(db):
    supported_instrument(db)
    bar = market_bar()
    service = HistoricalDataSyncService(db, StaticProvider([bar]))
    service.sync_symbol("US.QQQ", BarInterval.DAY_1, bar.timestamp_utc - timedelta(days=1), bar.timestamp_utc + timedelta(days=1))
    value = service.incremental_start("US.QQQ", BarInterval.DAY_1, bar.timestamp_utc - timedelta(days=100))
    assert value > bar.timestamp_utc - timedelta(days=10)


def test_overlap_windows():
    latest = datetime.now(timezone.utc)
    assert HistoricalDataSyncService.overlap_start(BarInterval.DAY_1, latest) == latest - timedelta(days=8)
    assert HistoricalDataSyncService.overlap_start(BarInterval.MIN_1, latest) == latest - timedelta(minutes=20)


def test_pagination_token():
    provider, quote, _ = make_provider([
        (0, Frame([raw_bar("101")]), b"next"),
        (0, Frame([dict(raw_bar("102"), time_key="2026-07-24 09:31:00")]), None),
    ])
    result = provider.fetch_bars(
        "US.QQQ", BarInterval.MIN_1,
        datetime(2026, 7, 23, tzinfo=timezone.utc),
        datetime(2026, 7, 25, tzinfo=timezone.utc),
        AdjustmentType.FORWARD,
    )
    assert len(result.bars) == 2
    assert result.pages_requested == 2
    assert quote.closed is True


def test_duplicate_pagination_token_stops_loop():
    provider, _, _ = make_provider([
        (0, Frame([raw_bar()]), b"same"),
        (0, Frame([]), b"same"),
    ])
    result = provider.fetch_bars(
        "US.QQQ", BarInterval.MIN_1,
        datetime(2026, 7, 23, tzinfo=timezone.utc),
        datetime(2026, 7, 25, tzinfo=timezone.utc),
        AdjustmentType.FORWARD,
    )
    assert result.error_code == HistoryErrorCode.PAGINATION_ERROR


def test_max_pages_stops_loop():
    provider, _, _ = make_provider([(0, Frame([raw_bar()]), b"next")], max_pages=1)
    result = provider.fetch_bars(
        "US.QQQ", BarInterval.MIN_1,
        datetime(2026, 7, 23, tzinfo=timezone.utc),
        datetime(2026, 7, 25, tzinfo=timezone.utc),
        AdjustmentType.FORWARD,
    )
    assert result.error_code == HistoryErrorCode.PAGINATION_ERROR


def test_permission_error_classification():
    assert classify_sdk_error("No quote permission") == HistoryErrorCode.PERMISSION_DENIED


def test_opend_unreachable_classification():
    manager = MoomooConnectionManager(socket_connector=lambda *a, **k: (_ for _ in ()).throw(OSError()))
    provider = MoomooHistoricalDataProvider(manager)
    result = provider.fetch_bars(
        "US.QQQ", BarInterval.DAY_1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        AdjustmentType.FORWARD,
    )
    assert result.error_code == HistoryErrorCode.OPEND_UNREACHABLE


def test_empty_result():
    provider, _, _ = make_provider([(0, Frame([]), None)])
    result = provider.fetch_bars(
        "US.QQQ", BarInterval.DAY_1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
        AdjustmentType.FORWARD,
    )
    assert result.error_code == HistoryErrorCode.EMPTY_RESULT


def test_single_symbol_failure_does_not_stop_others(db):
    supported_instrument(db)
    second = Instrument(
        symbol="US.SOXL", market="US", code="SOXL", is_supported=True,
        support_status="SUPPORTED", support_message="可用"
    )
    db.add(second)
    db.commit()
    service = HistoricalDataSyncService(db, StaticProvider(error=HistoryErrorCode.SDK_ERROR))
    jobs = service.sync_all(
        ["US.QQQ", "US.SOXL"], [BarInterval.DAY_1],
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    assert len(jobs) == 2
    assert all(job.status == "FAILED" for job in jobs)


def test_sync_job_status_and_data_issue(db):
    supported_instrument(db)
    invalid = market_bar(volume=-1)
    job = HistoricalDataSyncService(db, StaticProvider([invalid])).sync_symbol(
        "US.QQQ", BarInterval.DAY_1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    assert job.status == "SUCCESS"
    assert job.rows_skipped == 1
    assert db.scalar(select(func.count(HistoryDataIssue.id))) == 1
