from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.enums import BarInterval, RealtimeServiceState
from app.database.models import (
    CandidateSignal, Instrument, MarketBar, Opportunity, RealtimeBar,
    RuntimeStatus, WatchlistItem, WatchlistTimeframe,
)
from app.notifications.telegram import NotificationResult
from app.notifications.telegram_commands import TelegramCommandService
from app.runtime.opportunity_pipeline import OpportunityPipeline
from app.runtime.realtime_runtime import RealtimeOpportunityRuntime
from app.services.opportunity_service import OpportunityService


NOW = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)


def add_instrument_and_bar(db, symbol="SOXL", closed=True):
    instrument = Instrument(
        symbol="US." + symbol, market="US", code=symbol,
        is_active=True, is_supported=True,
    )
    db.add(instrument)
    db.flush()
    db.add(MarketBar(
        instrument_id=instrument.id, symbol="US." + symbol, interval="1m",
        timestamp_utc=NOW, timestamp_market=NOW, trading_date="2026-07-29",
        open=100, high=102, low=99, close=101, volume=1000,
        market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO",
    ))
    db.add(RealtimeBar(
        instrument_id=instrument.id, symbol="US." + symbol, interval="1m",
        timestamp_utc=NOW, timestamp_market=NOW, trading_date="2026-07-29",
        open=100, high=102, low=99, close=101, volume=1000, is_closed=closed,
        market_session="REGULAR", data_source="MOOMOO_REALTIME",
    ))
    db.commit()
    return instrument


def add_signal(db, kind="CANDIDATE_BUY", score=83, symbol="SOXL", timestamp=NOW):
    signal = CandidateSignal(
        symbol=symbol, market="US", timeframe="1m", bar_timestamp=timestamp,
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        parameters_hash="hash-%s-%s" % (kind, score), signal_type=kind, score=score, confidence=90,
        status="VALID", summary_zh="趋势回撤后重新转强",
        reasons_json=["趋势满足", "回撤满足"], risks_json=["成交量待确认"],
        feature_refs_json={"ema_20": {"version": "1.0.0"}},
        components_json={"trend_score": 30, "pullback_score": 20},
    )
    db.add(signal)
    db.commit()
    return signal


def test_opportunity_create_and_snapshot(db):
    add_instrument_and_bar(db)
    signal = add_signal(db)
    row, created = OpportunityService(db, min_score=70).from_signal(signal)
    assert created and row.direction == "LONG" and row.status == "DETECTED"
    assert row.feature_snapshot_json["feature_refs"]["ema_20"]["version"] == "1.0.0"
    assert row.strategy_snapshot_json["components"]["trend_score"] == 30


def test_opportunity_deduplication(db):
    add_instrument_and_bar(db)
    signal = add_signal(db)
    service = OpportunityService(db)
    first, first_created = service.from_signal(signal)
    second, second_created = service.from_signal(signal)
    assert first.id == second.id and first_created and not second_created
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 1


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_long_short_direction_enum(db, direction):
    add_instrument_and_bar(db)
    row, created = OpportunityService(db).from_signal(add_signal(db), direction)
    assert created and row.direction == direction


def test_invalid_direction_rejected(db):
    add_instrument_and_bar(db)
    with pytest.raises(ValueError):
        OpportunityService(db).from_signal(add_signal(db), "SIDEWAYS")


def test_status_change_and_expiry(db):
    add_instrument_and_bar(db)
    service = OpportunityService(db, expiry_bars=1)
    row, _ = service.from_signal(add_signal(db))
    service.update_status(row.id, "NOTIFIED", "123")
    assert row.status == "NOTIFIED" and row.notification_message_id == "123"
    expired = service.expire_due(NOW + timedelta(minutes=2))
    assert expired[0].status == "EXPIRED"


def test_later_confirmation_marks_existing_active_without_new_notice(db):
    add_instrument_and_bar(db)
    first_service = OpportunityService(db, expiry_bars=3)
    row, _ = first_service.from_signal(add_signal(db))
    second_service = OpportunityService(db, expiry_bars=3)
    confirmed, created = second_service.from_signal(add_signal(
        db, score=84, timestamp=NOW + timedelta(minutes=1),
    ))
    assert confirmed.id == row.id and confirmed.status == "ACTIVE" and not created
    assert db.scalar(select(func.count()).select_from(Opportunity)) == 1


def test_exit_invalidates_active_opportunity(db):
    add_instrument_and_bar(db)
    service = OpportunityService(db)
    row, _ = service.from_signal(add_signal(db))
    exit_signal = add_signal(db, "CANDIDATE_EXIT")
    service.from_signal(exit_signal)
    assert db.get(Opportunity, row.id).status == "INVALIDATED"


def test_watch_and_low_score_do_not_create(db):
    add_instrument_and_bar(db)
    service = OpportunityService(db, min_score=80)
    assert service.from_signal(add_signal(db, "WATCH")) == (None, False)
    assert service.from_signal(add_signal(db, score=79)) == (None, False)


class FakeManager:
    def __init__(self, connected=True):
        self.status = RealtimeServiceState.CONNECTED if connected else RealtimeServiceState.STOPPED
        self.connected = connected
        self.start_calls = 0

    def start(self):
        self.start_calls += 1
        self.status = RealtimeServiceState.CONNECTED
        self.connected = True

    def get_status(self):
        return SimpleNamespace(
            opend_connected=self.connected, last_message_at=NOW,
        )


class FakePipeline:
    def __init__(self, failures=None):
        self.failures = failures or set()
        self.calls = []

    def process_closed_bar(self, symbol, timeframe):
        self.calls.append((symbol, timeframe))
        if symbol in self.failures:
            return {"symbol": symbol, "status": "ERROR", "error": "测试错误"}
        return {"symbol": symbol, "status": "SUCCESS", "created": True}


def runtime_fixture(db, pipeline, connected=True):
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    return RealtimeOpportunityRuntime(
        Settings(runtime_poll_interval_seconds=.1),
        session_factory=factory, realtime_manager=FakeManager(connected),
        pipeline_factory=lambda session: pipeline,
    )


def add_watchlist(db, symbols):
    for symbol in symbols:
        item = WatchlistItem(
            symbol=symbol, market="US", role="TRADING", benchmark_symbol="QQQ",
            strategy_template="DEFAULT", enabled=True,
        )
        db.add(item)
        db.flush()
        db.add(WatchlistTimeframe(watchlist_item_id=item.id, timeframe="1m", enabled=True))
        add_instrument_and_bar(db, symbol)
    db.commit()


def test_unclosed_bar_not_processed(db):
    item = WatchlistItem(
        symbol="SOXL", market="US", role="TRADING", benchmark_symbol="QQQ",
        strategy_template="DEFAULT", enabled=True,
    )
    db.add(item)
    db.flush()
    db.add(WatchlistTimeframe(watchlist_item_id=item.id, timeframe="1m", enabled=True))
    add_instrument_and_bar(db, closed=False)
    pipeline = FakePipeline()
    result = runtime_fixture(db, pipeline).process_once()
    assert result["processed"] == 0 and pipeline.calls == []


def test_single_symbol_failure_isolated(db):
    add_watchlist(db, ["SOXL", "QQQ"])
    pipeline = FakePipeline({"SOXL"})
    result = runtime_fixture(db, pipeline).process_once()
    assert result["processed"] == 2
    assert {row["status"] for row in result["results"]} == {"SUCCESS", "ERROR"}


def test_runtime_restart_does_not_reprocess_same_bar_in_process(db):
    add_watchlist(db, ["SOXL"])
    pipeline = FakePipeline()
    runtime = runtime_fixture(db, pipeline)
    assert runtime.process_once()["processed"] == 1
    assert runtime.process_once()["processed"] == 0


def test_start_stop_idempotent(db):
    pipeline = FakePipeline()
    runtime = runtime_fixture(db, pipeline)
    first = runtime.start()
    second = runtime.start()
    assert not first["idempotent"] and second["idempotent"]
    runtime.stop()
    stopped = runtime.stop()
    assert stopped["status"] == "STOPPED" and stopped["idempotent"]


def test_opend_disconnect_recover_notification_dedup(db, monkeypatch):
    runtime = runtime_fixture(db, FakePipeline())
    events = []
    monkeypatch.setattr(runtime, "_notify_event", lambda subject, text: events.append(subject))
    runtime._last_opend_connected = True
    runtime.realtime_manager.connected = False
    runtime._check_connection_transition()
    runtime._check_connection_transition()
    runtime.realtime_manager.connected = True
    runtime._check_connection_transition()
    assert events == ["OpenD已断开", "OpenD已恢复"]


def test_runtime_status_persisted(db):
    runtime = runtime_fixture(db, FakePipeline())
    runtime._save_state(success=True)
    row = db.scalar(select(RuntimeStatus).where(RuntimeStatus.service_name == "realtime_runtime"))
    assert row.status == "STOPPED" and row.last_success_at is not None


def test_telegram_admin_and_non_admin(db):
    settings = Settings(telegram_admin_ids="42")
    service = TelegramCommandService(db, settings)
    assert service.handle("7", "/status")[0] is False
    assert service.handle("42", "/help")[0] is True


def test_why_contains_passed_and_failed(db):
    add_signal(db)
    ok, text = TelegramCommandService(db, Settings(telegram_admin_ids="42")).handle("42", "/why SOXL")
    assert ok and "通过条件" in text and "未通过或风险" in text
    assert "趋势满足" in text and "成交量待确认" in text


class FailedNotifier:
    async def send_text(self, message):
        return NotificationResult(status="failed", error="network")


def test_telegram_failure_records_without_crash(db):
    add_instrument_and_bar(db)
    opportunity, _ = OpportunityService(db).from_signal(add_signal(db))
    pipeline = OpportunityPipeline.__new__(OpportunityPipeline)
    pipeline.db = db
    pipeline.service = OpportunityService(db)
    pipeline.notifier = FailedNotifier()
    pipeline._notify_new(opportunity)
    db.refresh(opportunity)
    assert opportunity.notification_status == "FAILED"


def test_message_avoids_order_language(db):
    add_instrument_and_bar(db)
    opportunity, _ = OpportunityService(db).from_signal(add_signal(db))
    text = OpportunityPipeline.format_opportunity(opportunity)
    assert "交易机会" in text and "等待确认" in text
    assert "立即买入" not in text and "保证盈利" not in text
