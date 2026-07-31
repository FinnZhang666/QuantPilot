from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.database.models import CandidateSignal, FeatureValueRecord, Instrument, MarketBar, TradePlan
from app.market_snapshot.formatter import format_market_snapshot, format_market_snapshot_summary, format_snapshot_list, format_watchlist_snapshot
from app.market_snapshot.repository import MarketSnapshotRepository
from app.market_snapshot.service import MarketSnapshotService, SnapshotNotFound
from app.portfolio_center.errors import ValidationError
from app.portfolio_center.service import HoldingService, PortfolioService, WatchlistService


NOW = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)


def add_market(db, symbol="SOXL", price="32.15", feature=True):
    instrument = Instrument(symbol="US." + symbol, market="US", code=symbol, display_name=symbol + " Fund", is_supported=True)
    db.add(instrument); db.flush()
    db.add(MarketBar(
        instrument_id=instrument.id, symbol="US." + symbol, interval="1d",
        timestamp_utc=NOW, timestamp_market=NOW, trading_date="2026-07-31",
        open=price, high=price, low=price, close=price, volume=100,
        market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO",
    ))
    if feature:
        db.add(FeatureValueRecord(
            instrument_id=instrument.id, symbol="US." + symbol, interval="1d",
            timestamp_utc=NOW, feature_name="ema_20", feature_version="1.0.0",
            parameters_hash="hash", value_decimal=price, quality_status="VALID",
            source_bar_timestamp=NOW, data_source="MOOMOO", calculated_at=NOW,
        ))
    db.commit(); return instrument


def add_candidate(db, symbol="SOXL", kind="CANDIDATE_BUY"):
    row = CandidateSignal(
        symbol=symbol, market="US", timeframe="1d", bar_timestamp=NOW,
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        parameters_hash="p-" + symbol, signal_type=kind, score=80, confidence=90,
        status="VALID", summary_zh="test",
    )
    db.add(row); db.commit(); return row


def add_plan(db, symbol="SOXL", stage="PLAN"):
    row = TradePlan(
        plan_id="plan-" + symbol, symbol=symbol, market="US",
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        lifecycle_stage=stage, direction="LONG", timeframe="1d",
    )
    db.add(row); db.commit(); return row


def add_portfolio(db):
    return PortfolioService(db).create_portfolio("user-a", "Main")


def test_repository_get_normalizes_prefixed_market_data(db):
    add_market(db)
    raw = MarketSnapshotRepository(db).get_snapshot("soxl")
    assert raw["symbol"] == "SOXL" and raw["bar"].symbol == "US.SOXL"
    assert raw["feature"].feature_name == "ema_20"


def test_repository_list_empty_filter_pagination_sources(db):
    repository = MarketSnapshotRepository(db)
    assert list(repository.list_snapshots()) == []
    add_market(db, "QQQ"); add_market(db, "SOXL")
    rows = list(repository.list_snapshots(market="US"))
    assert [row["symbol"] for row in rows] == ["QQQ", "SOXL"]
    assert [row["symbol"] for row in repository.list_snapshots(symbol="soxl")] == ["SOXL"]
    assert [row["symbol"] for row in repository.list_snapshots(page=2, page_size=1)] == ["SOXL"]


def test_repository_watchlist_and_portfolio_snapshots_are_investment_only(db):
    add_market(db); portfolio = add_portfolio(db)
    WatchlistService(db).add_symbol(portfolio.id, "SOXL")
    assert len(list(MarketSnapshotRepository(db).list_watchlist_snapshots(portfolio.id))) == 1
    assert len(list(MarketSnapshotRepository(db).list_portfolio_snapshots(portfolio.id))) == 1


def test_snapshot_generation_market_feature_and_empty_links(db):
    add_market(db)
    row = MarketSnapshotService(db).get_snapshot("SOXL")
    assert row.latest_price == Decimal("32.15") and row.feature_status == "FEATURE_READY"
    assert row.candidate_signal == "NONE" and row.trade_plan_status == "NONE"
    assert row.holding == "NOT_HOLDING" and row.watching == "NOT_WATCHING"
    assert row.strategy_status == "UNKNOWN"


def test_strategy_status_no_data_watch_ready_active(db):
    db.add(Instrument(symbol="US.NODATA", market="US", code="NODATA", display_name="No Data")); db.commit()
    assert MarketSnapshotService(db).get_snapshot("NODATA").strategy_status == "NO_DATA"
    add_market(db, "WATCH"); p = add_portfolio(db); WatchlistService(db).add_symbol(p.id, "WATCH")
    assert MarketSnapshotService(db).get_snapshot("WATCH").strategy_status == "WATCH"
    add_market(db, "READY"); add_candidate(db, "READY")
    assert MarketSnapshotService(db).get_snapshot("READY").strategy_status == "READY"
    add_market(db, "ACTIVE"); add_plan(db, "ACTIVE")
    assert MarketSnapshotService(db).get_snapshot("ACTIVE").strategy_status == "ACTIVE"


@pytest.mark.parametrize("stage,is_active", [
    ("PLAN", True), ("COMPANION", True), ("REVIEW", False),
    ("CANCELLED", False), ("EXPIRED", False),
])
def test_trade_plan_stage_truth_and_active_mapping(db, stage, is_active):
    add_market(db); add_plan(db, stage=stage)
    row = MarketSnapshotService(db).get_snapshot("SOXL")
    assert row.trade_plan_status == stage
    assert (row.strategy_status == "ACTIVE") is is_active


def test_no_trade_plan_is_not_active(db):
    add_market(db)
    row = MarketSnapshotService(db).get_snapshot("SOXL")
    assert row.trade_plan_status == "NONE" and row.strategy_status != "ACTIVE"


def candidate(db, *, symbol="SOXL", market="US", status="VALID", version="1.0.0",
              offset=0, signal_type="WATCH", strategy="pullback_restrength"):
    row = CandidateSignal(
        symbol=symbol, market=market, timeframe="1d",
        bar_timestamp=NOW + timedelta(minutes=offset), strategy_name=strategy,
        strategy_version=version, parameters_hash="audit-%s-%s-%s" % (market, version, offset),
        signal_type=signal_type, score=80, confidence=90, status=status, summary_zh="audit",
    )
    db.add(row); db.commit(); return row


def test_candidate_selects_latest_valid_current_strategy(db):
    add_market(db)
    candidate(db, offset=1, signal_type="WATCH")
    candidate(db, offset=2, signal_type="CANDIDATE_BUY")
    assert MarketSnapshotService(db).get_snapshot("SOXL").candidate_signal == "BUY"


@pytest.mark.parametrize("ignored", [
    {"status": "ERROR", "offset": 5, "signal_type": "CANDIDATE_BUY"},
    {"status": "EXPIRED", "offset": 5, "signal_type": "CANDIDATE_BUY"},
    {"market": "HK", "offset": 5, "signal_type": "CANDIDATE_BUY"},
    {"symbol": "QQQ", "offset": 5, "signal_type": "CANDIDATE_BUY"},
    {"version": "0.9.0", "offset": 5, "signal_type": "CANDIDATE_BUY"},
    {"strategy": "other_strategy", "offset": 5, "signal_type": "CANDIDATE_BUY"},
])
def test_candidate_ignores_invalid_expired_or_wrong_identity(db, ignored):
    add_market(db); candidate(db, signal_type="WATCH"); candidate(db, **ignored)
    assert MarketSnapshotService(db).get_snapshot("SOXL").candidate_signal == "WATCH"


@pytest.mark.parametrize("kind,expected", [
    ("CANDIDATE_BUY", "BUY"), ("CANDIDATE_EXIT", "SELL"),
    ("CANDIDATE_REDUCE", "SELL"), ("WATCH", "WATCH"),
])
def test_candidate_status_mapping(db, kind, expected):
    symbol = "S" + str(abs(hash(kind)) % 100000)
    add_market(db, symbol); add_candidate(db, symbol, kind)
    assert MarketSnapshotService(db).get_snapshot(symbol).candidate_signal == expected


def test_holding_and_watchlist_status_weighted_cost(db):
    add_market(db); p = add_portfolio(db)
    service = HoldingService(db)
    first = service.open_holding(p.id, "SOXL", "US", "LONG", "2", "20")
    service.open_holding(p.id, "SOXL", "US", "LONG", "1", "29")
    WatchlistService(db).add_symbol(p.id, "SOXL")
    row = MarketSnapshotService(db).get_snapshot("SOXL", portfolio_id=p.id)
    assert row.holding == "HOLDING" and row.holding_quantity == Decimal("3")
    assert row.average_cost == Decimal("23") and row.watching == "WATCHING"
    assert row.holding_id in {first.id, first.id + 1} and row.portfolio_id == p.id


def test_missing_feature_candidate_holding_are_explicit(db):
    add_market(db, feature=False)
    row = MarketSnapshotService(db).get_snapshot("SOXL")
    assert row.feature_status == "FEATURE_MISSING"
    assert row.candidate_signal == "NONE" and row.holding == "NOT_HOLDING"


def test_empty_or_unknown_symbol_errors(db):
    with pytest.raises(ValidationError): MarketSnapshotService(db).get_snapshot("")
    with pytest.raises(SnapshotNotFound): MarketSnapshotService(db).get_snapshot("UNKNOWN")


def test_list_filters_pagination_stable_order_and_summary(db):
    for symbol in ("ZZZ", "AAA", "MMM"): add_market(db, symbol)
    add_candidate(db, "AAA")
    service = MarketSnapshotService(db)
    page, total = service.list_snapshots(candidate_signal="BUY", page=1, page_size=1)
    assert total == 1 and page[0].symbol == "AAA"
    all_rows, total = service.list_snapshots(page=1, page_size=2)
    assert total == 3 and [row.symbol for row in all_rows] == ["AAA", "MMM"]
    assert service.summary(all_rows)["total"] == 2


def test_service_is_read_only_and_request_cache(db):
    add_market(db); service = MarketSnapshotService(db)
    before = len(db.new), len(db.dirty), len(db.deleted)
    first = service.get_snapshot("SOXL"); second = service.get_snapshot("SOXL")
    assert first is second and before == (len(db.new), len(db.dirty), len(db.deleted))


def test_formatters_decimal_unicode_markdown_empty_and_summary(db):
    add_market(db, "SOXL"); row = MarketSnapshotService(db).get_snapshot("SOXL")
    assert "32.15" in format_market_snapshot(row)
    assert "Watchlist Snapshot" in format_watchlist_snapshot(row)
    assert "暂无数据" in format_snapshot_list([])
    assert "SOXL" in format_snapshot_list([row])
    assert "Candidate" in format_market_snapshot_summary(MarketSnapshotService.summary([row]))
    unsafe = replace(row, symbol="测_试*")
    assert "\\_" in format_market_snapshot(unsafe)
