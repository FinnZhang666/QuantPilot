from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.backtest.engine import BacktestEngine
from app.backtest.fees import adjusted_price, commission
from app.backtest.models import BacktestBar, BacktestConfig, BacktestSignal
from app.backtest.service import BacktestService
from app.database.models import (
    BacktestEquityPoint, BacktestRun, BacktestTrade, CandidateSignal,
    Instrument, MarketBar, StrategyParameterSet, WatchlistItem,
)
from sqlalchemy import func, select


def make_bars(count=25, start=None):
    start = start or datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        BacktestBar(
            timestamp=start + timedelta(days=index),
            open=Decimal(100 + index), high=Decimal(102 + index),
            low=Decimal(99 + index), close=Decimal(101 + index), volume=1000,
        )
        for index in range(count)
    ]


def config(bars, **kwargs):
    values = dict(
        symbol="SOXL", timeframe="1d", start_time=bars[0].timestamp,
        end_time=bars[-1].timestamp, parameters_hash="abc",
    )
    values.update(kwargs)
    return BacktestConfig(**values)


def signal(bar, kind):
    return BacktestSignal(bar.timestamp, kind, "abc")


def test_next_bar_open_entry_and_exit():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [
        signal(bars[1], "CANDIDATE_BUY"), signal(bars[5], "CANDIDATE_EXIT"),
    ])
    assert result.status == "SUCCESS"
    assert len(result.trades) == 1
    assert result.trades[0].entry_execution_timestamp == bars[2].timestamp
    assert result.trades[0].exit_execution_timestamp == bars[6].timestamp


def test_continuous_buy_is_deduplicated():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [
        signal(bars[1], "CANDIDATE_BUY"), signal(bars[2], "CANDIDATE_BUY"),
    ])
    assert len(result.trades) == 1


def test_exit_while_flat_does_nothing():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [signal(bars[2], "CANDIDATE_EXIT")])
    assert result.trades == []


def test_reduce_exits_long_and_preserves_trigger():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [
        signal(bars[1], "CANDIDATE_BUY"), signal(bars[5], "CANDIDATE_REDUCE"),
    ])
    assert result.trades[0].exit_signal_type == "CANDIDATE_REDUCE"


def test_last_signal_is_unfilled():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [signal(bars[-1], "CANDIDATE_BUY")])
    assert result.pending_actions[-1].status == "UNFILLED_END_OF_DATA"
    assert result.trades == []


def test_force_close_at_end():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [signal(bars[1], "CANDIDATE_BUY")])
    assert result.trades[0].status == "FORCED_CLOSED"
    assert result.metrics["forced_exit_count"] == 1
    assert result.metrics["open_position"] is False


def test_open_position_when_force_close_disabled():
    bars = make_bars()
    result = BacktestEngine().run(
        config(bars, force_close_at_end=False), bars, [signal(bars[1], "CANDIDATE_BUY")]
    )
    assert result.trades[0].status == "OPEN"
    assert result.metrics["open_position"] is True


def test_slippage_direction():
    assert adjusted_price(Decimal("100"), Decimal("10"), True) == Decimal("100.100")
    assert adjusted_price(Decimal("100"), Decimal("10"), False) == Decimal("99.900")


def test_commission_model():
    assert commission(10, Decimal("1"), Decimal(".1"), Decimal("3")) == Decimal("3")
    assert commission(100, Decimal("1"), Decimal(".1"), Decimal("3")) == Decimal("11")


def test_integer_shares_and_nonnegative_cash():
    bars = make_bars()
    result = BacktestEngine().run(
        config(bars, initial_cash=Decimal("1000")), bars, [signal(bars[1], "CANDIDATE_BUY")]
    )
    assert isinstance(result.trades[0].entry_shares, int)
    assert min(point.cash for point in result.equity_points) >= 0


def test_equity_point_for_every_bar():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [])
    assert len(result.equity_points) == len(bars)


def test_drawdown_is_nonpositive():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [])
    assert all(point.drawdown_pct <= 0 for point in result.equity_points)


def test_mae_and_mfe_are_calculated():
    bars = make_bars()
    result = BacktestEngine().run(config(bars), bars, [
        signal(bars[1], "CANDIDATE_BUY"), signal(bars[5], "CANDIDATE_EXIT"),
    ])
    assert result.trades[0].mae_pct is not None
    assert result.trades[0].mfe_pct is not None


def test_less_than_twenty_bars_is_diagnostic_only():
    bars = make_bars(19)
    result = BacktestEngine().run(config(bars), bars, [])
    assert result.status == "INSUFFICIENT_DATA"
    assert result.trades == []


def test_invalid_range_fails():
    bars = make_bars()
    result = BacktestEngine().run(
        config(bars, start_time=bars[-1].timestamp, end_time=bars[0].timestamp), bars, []
    )
    assert result.status == "FAILED"


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_invalid_price_fails(field):
    bars = make_bars()
    values = bars[3].__dict__.copy()
    values[field] = Decimal("0")
    bars[3] = BacktestBar(**values)
    assert BacktestEngine().run(config(bars), bars, []).status == "FAILED"


def test_negative_volume_fails():
    bars = make_bars()
    values = bars[3].__dict__.copy()
    values["volume"] = -1
    bars[3] = BacktestBar(**values)
    assert BacktestEngine().run(config(bars), bars, []).status == "FAILED"


def test_duplicate_bars_fail():
    bars = make_bars()
    bars[2] = bars[1]
    assert BacktestEngine().run(config(bars), bars, []).status == "FAILED"


def test_conflicting_signals_fail():
    bars = make_bars()
    signals = [signal(bars[2], "WATCH"), signal(bars[2], "CANDIDATE_BUY")]
    result = BacktestEngine().run(config(bars), bars, signals)
    assert "CONFLICTING_SIGNALS" in result.errors


def test_parameter_hash_mismatch_fails():
    bars = make_bars()
    signals = [BacktestSignal(bars[2].timestamp, "WATCH", "different")]
    assert BacktestEngine().run(config(bars), bars, signals).status == "FAILED"


def test_future_signals_do_not_change_past_equity():
    bars = make_bars()
    base = BacktestEngine().run(config(bars), bars, [signal(bars[1], "CANDIDATE_BUY")])
    changed = BacktestEngine().run(config(bars), bars, [
        signal(bars[1], "CANDIDATE_BUY"), signal(bars[-1], "CANDIDATE_EXIT"),
    ])
    assert base.equity_points[:-1] == changed.equity_points[:-1]


def seed_service_data(db):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    instrument = Instrument(
        symbol="US.SOXL", market="US", code="SOXL", is_supported=True,
    )
    db.add(instrument)
    db.flush()
    item = WatchlistItem(
        symbol="SOXL", market="US", role="TRADING", benchmark_symbol="QQQ",
        strategy_template="LEVERAGED_ETF", enabled=True,
    )
    db.add(item)
    db.flush()
    db.add(StrategyParameterSet(
        watchlist_item_id=item.id, strategy_name="pullback_restrength",
        strategy_version="1.0.0", parameters_json={}, parameters_hash="abc", enabled=True,
    ))
    for index in range(25):
        timestamp = start + timedelta(days=index)
        db.add(MarketBar(
            instrument_id=instrument.id, symbol="US.SOXL", interval="1d",
            timestamp_utc=timestamp, timestamp_market=timestamp,
            trading_date=timestamp.date().isoformat(), open=100 + index,
            high=102 + index, low=99 + index, close=101 + index, volume=1000,
            market_session="REGULAR", adjustment_type="FORWARD", data_source="MOOMOO",
        ))
        kind = "CANDIDATE_BUY" if index == 1 else ("CANDIDATE_EXIT" if index == 5 else "WATCH")
        db.add(CandidateSignal(
            symbol="SOXL", market="US", timeframe="1d", bar_timestamp=timestamp,
            strategy_name="pullback_restrength", strategy_version="1.0.0",
            parameters_hash="abc", signal_type=kind, score=50, confidence=100,
            status="VALID", summary_zh="测试", reasons_json=[], risks_json=[],
            feature_refs_json={}, components_json={},
        ))
    db.commit()
    return start


def test_service_persists_independent_run(db):
    start = seed_service_data(db)
    result = BacktestService(db).run(
        "SOXL", "1d", start, start + timedelta(days=24), parameters_hash="abc",
    )
    assert result["status"] == "SUCCESS"
    assert db.scalar(select(func.count()).select_from(BacktestRun)) == 1
    assert db.scalar(select(func.count()).select_from(BacktestTrade)) == 1
    assert db.scalar(select(func.count()).select_from(BacktestEquityPoint)) == 25


def test_duplicate_configuration_creates_new_run(db):
    start = seed_service_data(db)
    service = BacktestService(db)
    first = service.run("SOXL", "1d", start, start + timedelta(days=24), parameters_hash="abc")
    second = service.run("SOXL", "1d", start, start + timedelta(days=24), parameters_hash="abc")
    assert first["run_id"] != second["run_id"]
    assert second["duplicate_configuration"] is True
    assert first["run_id"] in second["existing_run_ids"]
