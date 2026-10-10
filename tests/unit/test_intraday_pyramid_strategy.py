from datetime import datetime, timezone
from decimal import Decimal

from app.strategy.models import StrategyInput
from app.strategy.strategies.intraday_pyramid import (
    IntradayPyramidStrategy, PyramidPositionState,
)


def strategy_input(**changes):
    features = {
        "ema_20": Decimal("102"), "ema_60": Decimal("100"),
        "ema20_slope_5": Decimal("0.8"), "close_vs_ema20_pct": Decimal("0.5"),
        "close_vs_vwap_pct": Decimal("0.8"), "return_1": Decimal("0.6"),
        "volume_ratio_20": Decimal("1.8"), "close_location_value": Decimal("0.8"),
        "atr_pct_14": Decimal("2.0"), "rsi_14": Decimal("61"),
    }
    features.update(changes.pop("feature_changes", {}))
    return StrategyInput(
        symbol="MU", market="US", timeframe=changes.pop("timeframe", "5m"),
        bar_timestamp=datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc),
        enabled=True, role="TRADING", validation_status="VALID", benchmark_symbol="SOXX",
        parameters={}, parameters_hash="test", features=features,
        feature_statuses={name: "VALID" for name in features}, feature_refs={}, **changes,
    )


def test_strong_closed_bar_generates_research_candidate():
    result = IntradayPyramidStrategy().evaluate(strategy_input())
    assert result.signal_type == "CANDIDATE_BUY"
    assert result.score == 100
    assert any("RESEARCH" in risk for risk in result.risks)


def test_weak_volume_remains_watch():
    result = IntradayPyramidStrategy().evaluate(strategy_input(
        feature_changes={"volume_ratio_20": Decimal("0.8")},
    ))
    assert result.signal_type == "WATCH"
    assert "成交量不足" in result.risks


def test_only_5m_and_15m_are_supported():
    assert IntradayPyramidStrategy().evaluate(strategy_input(timeframe="1d")).signal_type == "SKIPPED"


def test_losing_position_never_adds():
    decision = IntradayPyramidStrategy().decide_position(PyramidPositionState(
        stage=0, current_return_pct=Decimal("-1"), current_allocation=Decimal("0.15"),
        trend_confirmed=True,
    ))
    assert decision.action == "HOLD"
    assert decision.add_allocation == 0
    assert "禁止补仓" in decision.reason


def test_profitable_position_adds_without_exceeding_cap():
    strategy = IntradayPyramidStrategy()
    first = strategy.decide_position(PyramidPositionState(
        stage=0, current_return_pct=Decimal("2"), current_allocation=Decimal("0.15"),
        trend_confirmed=True,
    ))
    final = strategy.decide_position(PyramidPositionState(
        stage=2, current_return_pct=Decimal("6"), current_allocation=Decimal("0.45"),
        trend_confirmed=True,
    ))
    assert (first.action, first.next_stage, first.target_allocation) == ("ADD", 1, Decimal("0.30"))
    assert final.action == "ADD"
    assert final.target_allocation == Decimal("0.70")


def test_stop_or_reversal_exits_instead_of_adding():
    decision = IntradayPyramidStrategy().decide_position(PyramidPositionState(
        stage=1, current_return_pct=Decimal("5"), current_allocation=Decimal("0.30"),
        trend_confirmed=True, stop_triggered=True,
    ))
    assert decision.action == "EXIT"
    assert decision.target_allocation == 0
