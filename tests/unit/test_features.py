from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.enums import BarInterval, FeatureQualityStatus, FeatureValueType
from app.database.models import FeatureDefinitionRecord, FeatureQualityIssue, FeatureValueRecord, Instrument, MarketBar, RealtimeBar
from app.features.calculator import ANNUALIZATION_FACTORS, FeatureCalculator
from app.features.definitions import DEFAULT_DEFINITIONS
from app.features.incremental import RealtimeFeatureUpdater
from app.features.models import FeatureDefinition
from app.features.pipeline import FeatureCalculationService
from app.features.quality import FeatureQualityService
from app.features.registry import FeatureRegistry, parameters_hash
from app.features.repository import FeatureRepository
from app.features.validation import validate_input_bars


def sample_frame(count=300, interval="D"):
    index = pd.date_range("2025-01-01", periods=count, freq=interval, tz="UTC")
    close = pd.Series(np.linspace(100, 200, count), index=index)
    return pd.DataFrame({
        "open": close - 0.5, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.arange(count) + 100,
        "turnover": (np.arange(count) + 100) * close,
        "trading_date": [item.date().isoformat() for item in index],
        "market_session": ["REGULAR"] * count,
    }, index=index)


def calculations(count=300):
    frame = sample_frame(count)
    return frame, FeatureCalculator().calculate(frame, "1d", {"US.QQQ": frame, "US.SOXX": frame})


def test_feature_definition_registration():
    registry = FeatureRegistry.defaults()
    assert len(registry.list()) == 73 and registry.get("ema_20").version == "1.0.0"


@pytest.mark.parametrize("feature_name", sorted(DEFAULT_DEFINITIONS))
def test_every_registered_feature_has_calculator_output(feature_name):
    frame = sample_frame()
    output = FeatureCalculator().calculate(frame, "1d")
    assert feature_name in output
    assert output[feature_name].index.equals(frame.index)


def test_duplicate_registration_rejected():
    registry = FeatureRegistry()
    item = DEFAULT_DEFINITIONS["ema_20"]
    registry.register(item)
    with pytest.raises(ValueError):
        registry.register(item)


def test_version_is_part_of_registry_key():
    registry = FeatureRegistry()
    item = DEFAULT_DEFINITIONS["ema_20"]
    registry.register(item)
    registry.register(replace(item, version="2.0.0"))
    assert len(registry.list()) == 2


def test_parameter_hash_stable_and_sensitive():
    assert parameters_hash({"b": 2, "a": 1}) == parameters_hash({"a": 1, "b": 2})
    assert parameters_hash({"a": 1}) != parameters_hash({"a": 2})


@pytest.mark.parametrize("period", [5, 10, 20, 50, 200])
def test_sma(period):
    frame, result = calculations()
    expected = frame["close"].iloc[-period:].mean()
    assert result["sma_%s" % period].iloc[-1] == pytest.approx(expected)


@pytest.mark.parametrize("period", [5, 10, 20, 50, 60, 200])
def test_ema_adjust_false(period):
    frame, result = calculations()
    expected = frame["close"].ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
    assert result["ema_%s" % period].iloc[-1] == pytest.approx(expected)
    assert result["ema_%s" % period].iloc[period - 2] != result["ema_%s" % period].iloc[period - 2]


def test_rsi_wilder_range():
    _, result = calculations()
    assert result["rsi_14"].iloc[-1] == pytest.approx(100)
    assert result["rsi_14"].dropna().between(0, 100).all()


def test_macd_formula():
    frame, result = calculations()
    expected = frame.close.ewm(span=12, adjust=False, min_periods=12).mean() - frame.close.ewm(span=26, adjust=False, min_periods=26).mean()
    assert result["macd_line_12_26"].iloc[-1] == pytest.approx(expected.iloc[-1])
    assert result["macd_histogram"].iloc[-1] == pytest.approx(result["macd_line_12_26"].iloc[-1] - result["macd_signal_9"].iloc[-1])


def test_true_range_and_atr_wilder():
    frame, result = calculations()
    expected_tr = max(frame.high.iloc[-1] - frame.low.iloc[-1], abs(frame.high.iloc[-1] - frame.close.iloc[-2]), abs(frame.low.iloc[-1] - frame.close.iloc[-2]))
    assert result["true_range"].iloc[-1] == pytest.approx(expected_tr)
    expected_atr = result["true_range"].ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().iloc[-1]
    assert result["atr_14"].iloc[-1] == pytest.approx(expected_atr)


def test_bollinger_and_zero_width():
    frame, result = calculations()
    assert result["bollinger_upper_20_2"].iloc[-1] >= result["bollinger_mid_20"].iloc[-1] >= result["bollinger_lower_20_2"].iloc[-1]
    flat = sample_frame(30)
    flat[["open", "high", "low", "close"]] = 10
    values = FeatureCalculator().calculate(flat, "1d")
    assert pd.isna(values["bollinger_position"].iloc[-1])


def test_returns_log_returns_and_roc():
    frame, result = calculations()
    expected = frame.close.iloc[-1] / frame.close.iloc[-2] - 1
    assert result["return_1"].iloc[-1] == pytest.approx(expected)
    assert result["log_return_1"].iloc[-1] == pytest.approx(np.log1p(expected))
    assert result["roc_10"].iloc[-1] == pytest.approx(result["return_10"].iloc[-1] * 100)


@pytest.mark.parametrize("interval", ["1d", "60m", "15m", "5m", "1m"])
def test_realized_volatility_annualization(interval):
    frame = sample_frame()
    result = FeatureCalculator().calculate(frame, interval)
    expected = result["log_return_1"].rolling(20).std(ddof=1).iloc[-1] * np.sqrt(ANNUALIZATION_FACTORS[interval])
    assert result["realized_volatility_20"].iloc[-1] == pytest.approx(expected)


def test_volume_ratio_excludes_current():
    frame = sample_frame(30)
    result = FeatureCalculator().calculate(frame, "1d")
    expected = frame.volume.iloc[-1] / frame.volume.iloc[-21:-1].mean()
    assert result["volume_ratio_20"].iloc[-1] == pytest.approx(expected)


def test_vwap_resets_and_zero_volume():
    frame = sample_frame(4, "min")
    frame["trading_date"] = ["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-02"]
    result = FeatureCalculator().calculate(frame, "1m")
    typical = (frame.high.iloc[2] + frame.low.iloc[2] + frame.close.iloc[2]) / 3
    assert result["session_vwap_regular"].iloc[2] == pytest.approx(typical)
    frame["volume"] = 0
    assert pd.isna(FeatureCalculator().calculate(frame, "1m")["session_vwap_regular"].iloc[-1])


def test_gap_open_daily_and_minute_inheritance():
    frame = sample_frame(4)
    result = FeatureCalculator().calculate(frame, "1d")
    assert result["gap_open_pct"].iloc[1] == pytest.approx(frame.open.iloc[1] / frame.close.iloc[0] - 1)
    minute = sample_frame(4, "min")
    minute["trading_date"] = ["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-02"]
    gap = FeatureCalculator().calculate(minute, "1m")["gap_open_pct"]
    assert gap.iloc[2] == gap.iloc[3]


@pytest.mark.parametrize("name", ["body_range_ratio", "upper_wick_ratio", "lower_wick_ratio", "close_location_value"])
def test_price_action_is_finite(name):
    _, result = calculations()
    assert np.isfinite(result[name].iloc[-1])


def test_close_location_uses_zero_to_one_scale():
    frame = sample_frame(2)
    frame.loc[frame.index[-1], ["low", "high", "close"]] = [100, 110, 102]
    value = FeatureCalculator().calculate(frame, "1d")["close_location_value"].iloc[-1]
    assert value == pytest.approx(0.2)


def test_rolling_high_breakout_excludes_current():
    frame = sample_frame(30)
    frame.loc[frame.index[-1], "high"] = 1000
    frame.loc[frame.index[-1], "close"] = 999
    result = FeatureCalculator().calculate(frame, "1d")
    prior_high = frame.high.shift(1).rolling(20).max().iloc[-1]
    assert result["breakout_high_20_pct"].iloc[-1] == pytest.approx((999 / prior_high - 1) * 100)
    assert result["distance_from_high_20_pct"].iloc[-1] <= 0


def test_drawdown_and_low_distance():
    _, result = calculations()
    assert result["drawdown_from_20_high_pct"].iloc[-1] <= 0
    assert result["distance_from_low_20_pct"].iloc[-1] >= 0


def test_relative_strength_exact_alignment_and_missing_reference():
    frame = sample_frame()
    shifted = frame.copy()
    shifted.index = shifted.index + timedelta(hours=1)
    no_match = FeatureCalculator().calculate(frame, "1d", {"US.QQQ": shifted})
    assert no_match["relative_return_qqq_20"].isna().all()
    aligned = FeatureCalculator().calculate(frame, "1d", {"US.QQQ": frame})
    assert aligned["relative_return_qqq_20"].iloc[-1] == pytest.approx(0)
    missing = FeatureCalculator().calculate(frame, "1d")
    assert missing["relative_return_soxx_20"].isna().all()


def test_market_environment_features():
    frame, result = calculations()
    assert result["market_qqq_return_1"].iloc[-1] == pytest.approx(frame.close.pct_change(fill_method=None).iloc[-1])
    assert "market_soxx_close_vs_ema20_pct" in result


def test_future_modification_does_not_change_past():
    frame = sample_frame()
    first = FeatureCalculator().calculate(frame, "1d")
    changed = frame.copy()
    changed.iloc[-1, changed.columns.get_loc("close")] = 99999
    second = FeatureCalculator().calculate(changed, "1d")
    for name in ("ema_20", "atr_14", "rsi_14", "breakout_high_20_pct"):
        assert first[name].iloc[-2] == pytest.approx(second[name].iloc[-2])


def test_truncated_input_common_point_matches():
    frame = sample_frame()
    full = FeatureCalculator().calculate(frame, "1d")
    truncated = FeatureCalculator().calculate(frame.iloc[:-10], "1d")
    assert full["ema_20"].iloc[-11] == pytest.approx(truncated["ema_20"].iloc[-1])


def test_input_validation():
    frame = sample_frame(3)
    frame.iloc[1, frame.columns.get_loc("high")] = -1
    assert "INPUT_INVALID" in validate_input_bars(frame)


def test_quality_rejects_nonfinite_and_ranges():
    service = FeatureQualityService()
    assert "OUTPUT_NOT_FINITE" in service.validate_output("ema_20", pd.Series([np.inf]))
    assert "OUTPUT_OUT_OF_RANGE" in service.validate_output("rsi_14", pd.Series([101.0]))


def add_bars(db, count=40, realtime=False, closed=True):
    instrument = Instrument(symbol="US.QQQ", market="US", code="QQQ", is_supported=True, support_status="SUPPORTED", support_message="可用")
    db.add(instrument)
    db.flush()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    model = RealtimeBar if realtime else MarketBar
    for i in range(count):
        kwargs = dict(instrument_id=instrument.id, symbol="US.QQQ", interval="1m" if realtime else "1d", timestamp_utc=base + timedelta(minutes=i) if realtime else base + timedelta(days=i), timestamp_market=base, trading_date=(base + timedelta(days=i)).date().isoformat(), open=Decimal(100 + i), high=Decimal(102 + i), low=Decimal(99 + i), close=Decimal(101 + i), volume=100 + i, turnover=Decimal(10000), market_session="REGULAR", data_source="MOOMOO")
        if realtime:
            kwargs["is_closed"] = closed
        else:
            kwargs.update(adjustment_type="FORWARD", is_blank=False)
        db.add(model(**kwargs))
    db.commit()


def test_definition_init_and_feature_upsert_decimal(db):
    add_bars(db)
    repo = FeatureRepository(db)
    repo.initialize_definitions(FeatureRegistry.defaults().list())
    service = FeatureCalculationService(repo)
    service.calculate_symbol("US.QQQ", BarInterval.DAY_1, ["ema_20"])
    service.calculate_symbol("US.QQQ", BarInterval.DAY_1, ["ema_20"])
    rows = db.scalars(select(FeatureValueRecord)).all()
    assert len(rows) == 40 and isinstance(rows[-1].value_decimal, Decimal)
    assert db.query(FeatureDefinitionRecord).count() == 73


def test_warmup_and_missing_values_are_explicit(db):
    add_bars(db, 10)
    FeatureCalculationService(FeatureRepository(db)).calculate_symbol("US.QQQ", BarInterval.DAY_1, ["ema_20"])
    rows = db.scalars(select(FeatureValueRecord)).all()
    assert all(row.quality_status == "WARMUP" for row in rows)


def test_missing_reference_is_persisted_once(db):
    add_bars(db, 30)
    service = FeatureCalculationService(FeatureRepository(db))
    service.calculate_symbol("US.QQQ", BarInterval.DAY_1, ["relative_return_soxx_20"])
    service.calculate_symbol("US.QQQ", BarInterval.DAY_1, ["relative_return_soxx_20"])
    rows = db.scalars(select(FeatureQualityIssue)).all()
    assert len(rows) == 1
    assert rows[0].issue_type == "REFERENCE_DATA_MISSING"
    assert db.query(FeatureValueRecord).filter_by(quality_status="MISSING").count() > 0


def test_invalid_input_stops_feature_persistence(db):
    add_bars(db, 30)
    bar = db.scalar(select(MarketBar).order_by(MarketBar.id.desc()))
    bar.high = Decimal("-1")
    db.commit()
    job = FeatureCalculationService(FeatureRepository(db)).calculate_symbol(
        "US.QQQ", BarInterval.DAY_1, ["ema_20"]
    )
    assert job.status == "FAILED"
    assert db.query(FeatureValueRecord).count() == 0


def test_unclosed_realtime_bar_not_used(db):
    add_bars(db, 5, realtime=True, closed=False)
    job = FeatureCalculationService(FeatureRepository(db)).calculate_realtime_closed("US.QQQ", ["return_1"])
    assert job.status == "SKIPPED" and db.query(FeatureValueRecord).count() == 0


def test_closed_realtime_bar_incremental_is_idempotent(db):
    add_bars(db, 5, realtime=True, closed=True)
    service = FeatureCalculationService(FeatureRepository(db))
    service.calculate_realtime_closed("US.QQQ", ["return_1"])
    service.calculate_realtime_closed("US.QQQ", ["return_1"])
    assert db.query(FeatureValueRecord).count() == 5


def test_realtime_updater_initializes(db):
    updater = RealtimeFeatureUpdater(FeatureCalculationService(FeatureRepository(db)))
    assert updater.service is not None
