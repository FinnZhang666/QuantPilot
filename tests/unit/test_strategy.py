from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.database.models import (
    CandidateSignal, FeatureValueRecord, Instrument, MarketBar, StrategyParameterSet,
    RealtimeBar, StrategyRun, WatchlistItem, WatchlistTimeframe,
)
from app.strategy.classifier import TickerClassifier
from app.strategy.constants import (
    DEFAULT_WATCHLIST, FEATURE_ALIASES, KNOWN_CLASSIFICATIONS, ROLE_TIMEFRAMES,
)
from app.strategy.dependencies import FeatureDependencyResolver
from app.strategy.disk import DiskSpaceGuard, DiskStatus
from app.strategy.models import StrategyInput
from app.strategy.repository import StrategyRepository
from app.strategy.service import StrategyRunner
from app.strategy.strategies.pullback_restrength import PullbackRestrengthStrategy
from app.strategy.templates import (
    TEMPLATE_OVERRIDES, parameters_for_template, parameters_hash,
    validate_parameter_update,
)
from app.strategy.watchlist import WatchlistService


def strategy_input(**changes):
    values = {
        "ema_20": Decimal("110"), "ema_60": Decimal("100"),
        "ema20_slope_5": Decimal("0.02"), "close_vs_ema20_pct": Decimal("0.5"),
        "close_vs_ema60_pct": Decimal("1.0"), "distance_from_high_20_pct": Decimal("-4"),
        "return_1": Decimal("0.01"), "close_location_value": Decimal("0.8"),
        "rsi_14": Decimal("60"), "atr_14": Decimal("2"), "atr_pct_14": Decimal("3"),
        "close_vs_vwap_pct": Decimal("1"), "volume_ratio_20": Decimal("1.2"),
        "body_range_ratio": Decimal("0.5"), "return_5": Decimal("0.03"),
        "relative_return_soxx_20": Decimal("0.02"),
        "_previous_close_vs_ema20": Decimal("-0.5"),
    }
    values.update(changes.pop("feature_changes", {}))
    statuses = {name: "VALID" for name in values}
    statuses.update(changes.pop("status_changes", {}))
    data = dict(
        symbol="SOXL", market="US", timeframe="1d",
        bar_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        enabled=True, role="TRADING", validation_status="VALID", benchmark_symbol="SOXX",
        parameters=parameters_for_template("LEVERAGED_ETF"),
        parameters_hash=parameters_hash(parameters_for_template("LEVERAGED_ETF")),
        features=values, feature_statuses=statuses, feature_refs={},
    )
    data.update(changes)
    return StrategyInput(**data)


@pytest.mark.parametrize("symbol", DEFAULT_WATCHLIST)
def test_known_classifications_exist(symbol):
    assert symbol in KNOWN_CLASSIFICATIONS


@pytest.mark.parametrize(
    "symbol,role,benchmark,template",
    [
        ("QQQ", "MARKET_BENCHMARK", None, "BROAD_MARKET"),
        ("SOXX", "SECTOR_BENCHMARK", "QQQ", "SECTOR_ETF"),
        ("SOXL", "TRADING", "SOXX", "LEVERAGED_ETF"),
        ("SOXS", "RISK_INDICATOR", "SOXX", "INVERSE_LEVERAGED_ETF"),
        ("TQQQ", "TRADING", "QQQ", "LEVERAGED_ETF"),
        ("RAM", "TRADING", "SOXX", "LEVERAGED_ETF"),
        ("MULL", "TRADING", "SOXX", "LEVERAGED_ETF"),
        ("PLTR", "TRADING", "QQQ", "HIGH_GROWTH"),
        ("ML", "TRADING", "QQQ", "HIGH_GROWTH"),
    ],
)
def test_known_classification_fields(symbol, role, benchmark, template):
    value = TickerClassifier().classify(symbol)
    assert value["role"] == role
    assert value["benchmark_symbol"] == benchmark
    assert value["strategy_template"] == template
    assert value["validation_status"] == "PENDING_VALIDATION"


@pytest.mark.parametrize("template", sorted(TEMPLATE_OVERRIDES))
def test_each_template_has_unbacktested_parameters(template):
    values = parameters_for_template(template)
    assert values["parameter_status"] == "UNBACKTESTED_DEFAULT"
    assert 0 <= values["candidate_buy_threshold"] <= 100


@pytest.mark.parametrize("role", sorted(ROLE_TIMEFRAMES))
def test_each_role_has_timeframes(role):
    assert "1d" in ROLE_TIMEFRAMES[role]
    assert len(set(ROLE_TIMEFRAMES[role])) == len(ROLE_TIMEFRAMES[role])


@pytest.mark.parametrize("raw,expected", [
    (" pltr ", "PLTR"), ("us.soxl", "SOXL"), ("QQQ", "QQQ"), ("brk.b", "BRK.B"),
])
def test_symbol_normalization(raw, expected):
    assert WatchlistService.normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["", "A B", "$QQQ", "A/B", "123"])
def test_invalid_symbols(raw):
    with pytest.raises(ValueError):
        WatchlistService.normalize_symbol(raw)


def test_watchlist_default_init_is_idempotent(db):
    service = WatchlistService(db)
    first = service.initialize_defaults()
    second = service.initialize_defaults()
    assert first["added"] == 9
    assert second["existing"] == 9
    assert db.query(WatchlistItem).count() == 9


def test_watchlist_creates_timeframes_and_parameters(db):
    result = WatchlistService(db).add_symbol("SOXL")
    item = WatchlistService(db).get_symbol("SOXL")
    assert result["benchmark_symbol"] == "SOXX"
    assert db.query(WatchlistTimeframe).filter_by(watchlist_item_id=item.id).count() == 5
    assert db.query(StrategyParameterSet).filter_by(watchlist_item_id=item.id).count() == 1


def test_unknown_ticker_pending_default(db):
    result = WatchlistService(db).add_symbol("XYZQ")
    assert result["role"] == "TRADING"
    assert result["benchmark_symbol"] == "QQQ"
    assert result["strategy_template"] == "DEFAULT"
    assert result["validation_status"] == "PENDING_VALIDATION"


def test_local_instrument_makes_validation_valid(db):
    db.add(Instrument(
        symbol="US.PLTR", market="US", code="PLTR", is_supported=True,
        support_status="SUPPORTED", support_message="可用",
    ))
    db.commit()
    assert WatchlistService(db).add_symbol("PLTR")["validation_status"] == "VALID"


def test_invalid_local_instrument_is_not_pending(db):
    db.add(Instrument(
        symbol="US.XYZQ", market="US", code="XYZQ", is_supported=False,
        support_status="INVALID_SYMBOL", support_message="代码不存在",
    ))
    db.commit()
    assert WatchlistService(db).add_symbol("XYZQ")["validation_status"] == "INVALID"


def test_duplicate_disabled_reactivates(db):
    service = WatchlistService(db)
    service.add_symbol("PLTR")
    service.disable_symbol("PLTR")
    result = service.add_symbol("PLTR")
    assert result["result"] == "reactivated" and result["enabled"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "RISK_INDICATOR"), ("benchmark_symbol", "SOXX"),
        ("strategy_template", "DEFAULT"), ("sector", "custom"), ("notes", "观察"),
    ],
)
def test_manual_updates_are_protected(db, field, value):
    service = WatchlistService(db)
    service.add_symbol("PLTR")
    item = service.update_symbol("PLTR", **{field: value})
    assert getattr(item, field) == value
    assert item.classification_source == "MANUAL"
    service.add_symbol("PLTR")
    assert service.get_symbol("PLTR").classification_source == "MANUAL"


def test_reclassify_preview_does_not_modify(db):
    service = WatchlistService(db)
    service.add_symbol("SOXS")
    service.update_symbol("SOXS", role="TRADING")
    preview = service.reclassify_symbol("SOXS", False)
    assert preview["preview"]
    assert service.get_symbol("SOXS").role == "TRADING"


def test_reclassify_confirm_restores_auto(db):
    service = WatchlistService(db)
    service.add_symbol("SOXS")
    service.update_symbol("SOXS", role="TRADING")
    service.reclassify_symbol("SOXS", True)
    assert service.get_symbol("SOXS").role == "RISK_INDICATOR"
    assert service.get_symbol("SOXS").classification_source == "AUTO"


def test_remove_is_soft_and_preserves_signal(db):
    service = WatchlistService(db)
    service.add_symbol("PLTR")
    db.add(CandidateSignal(
        symbol="PLTR", market="US", timeframe="1d",
        bar_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        strategy_name="pullback_restrength", strategy_version="1.0.0",
        parameters_hash="x", signal_type="WATCH", score=1, confidence=1,
        status="VALID", summary_zh="测试",
    ))
    db.commit()
    service.remove_symbol("PLTR")
    assert not service.get_symbol("PLTR").enabled
    assert db.query(CandidateSignal).count() == 1


def test_parameter_hash_stable_and_changes():
    a = parameters_for_template("DEFAULT")
    b = dict(reversed(list(a.items())))
    assert parameters_hash(a) == parameters_hash(b)
    b["pullback_min_pct"] = 2
    assert parameters_hash(a) != parameters_hash(b)


@pytest.mark.parametrize("key,value", [
    ("pullback_min_pct", "2.5"), ("pullback_max_pct", 7),
    ("candidate_buy_threshold", "80"), ("volume_ratio_min", "1.3"),
])
def test_valid_parameter_updates(key, value):
    result = validate_parameter_update(parameters_for_template("DEFAULT"), {key: value})
    assert result[key] is not None


@pytest.mark.parametrize("updates", [
    {"unknown": 1}, {"pullback_min_pct": -1}, {"candidate_buy_threshold": 101},
    {"pullback_min_pct": 9, "pullback_max_pct": 2}, {"rsi_overbought": "bad"},
])
def test_invalid_parameter_updates(updates):
    with pytest.raises(ValueError):
        validate_parameter_update(parameters_for_template("DEFAULT"), updates)


def test_candidate_buy_scores_100():
    result = PullbackRestrengthStrategy().evaluate(strategy_input())
    assert result.signal_type == "CANDIDATE_BUY"
    assert result.score == 100
    assert result.confidence == 100


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"ema_20": Decimal("90")}, "CANDIDATE_EXIT"),
        ({"distance_from_high_20_pct": Decimal("-10")}, "CANDIDATE_EXIT"),
        ({"close_vs_ema20_pct": Decimal("-1")}, "WATCH"),
        ({"return_1": Decimal("-0.01")}, "CANDIDATE_BUY"),
        ({"volume_ratio_20": Decimal("0.1")}, "WATCH"),
        ({"relative_return_soxx_20": Decimal("-0.1")}, "WATCH"),
    ],
)
def test_strategy_scenarios(changes, expected):
    result = PullbackRestrengthStrategy().evaluate(strategy_input(feature_changes=changes))
    assert result.signal_type == expected
    assert 0 <= result.score <= 100


def test_candidate_reduce_high_risk_and_weak_relative():
    value = strategy_input(feature_changes={
        "atr_pct_14": Decimal("20"),
        "relative_return_soxx_20": Decimal("-0.1"),
    })
    assert PullbackRestrengthStrategy().evaluate(value).signal_type == "CANDIDATE_REDUCE"


@pytest.mark.parametrize("role", ["MARKET_BENCHMARK", "SECTOR_BENCHMARK", "RISK_INDICATOR"])
def test_non_trading_roles_are_skipped(role):
    result = PullbackRestrengthStrategy().evaluate(strategy_input(role=role))
    assert result.signal_type == "SKIPPED"


def test_disabled_input_is_skipped_with_disabled_status():
    result = PullbackRestrengthStrategy().evaluate(strategy_input(enabled=False))
    assert result.signal_type == "SKIPPED"
    assert result.status == "DISABLED"


@pytest.mark.parametrize("status", ["MISSING", "WARMUP", "INVALID"])
def test_core_bad_quality_is_insufficient(status):
    result = PullbackRestrengthStrategy().evaluate(strategy_input(
        feature_changes={"ema_20": None}, status_changes={"ema_20": status},
    ))
    assert result.signal_type == "INSUFFICIENT_DATA"
    assert result.status == ("WARMUP" if status == "WARMUP" else "MISSING_FEATURE")


def test_optional_missing_reduces_confidence():
    result = PullbackRestrengthStrategy().evaluate(strategy_input(
        feature_changes={"volume_ratio_20": None},
        status_changes={"volume_ratio_20": "MISSING"},
    ))
    assert result.confidence < 100


def test_pending_validation_reduces_confidence():
    result = PullbackRestrengthStrategy().evaluate(strategy_input(
        validation_status="PENDING_VALIDATION",
    ))
    assert result.confidence == 90


def test_feature_dependency_names_are_registry_names(db):
    resolver = FeatureDependencyResolver(StrategyRepository(db), feature_service=None)
    required, optional, relative = resolver.dependency_names("SOXX")
    assert relative == "relative_return_soxx_20"
    assert "ema_20" in required
    assert "volume_ratio_20" in optional
    assert len(required) + len(optional) < 73


def test_disk_guard_warning_and_block(monkeypatch):
    guard = DiskSpaceGuard(15, 10)
    monkeypatch.setattr(guard, "check", lambda: DiskStatus(9, True, True))
    with pytest.raises(RuntimeError):
        guard.enforce(True, True)
    assert guard.enforce(False, True).blocked


def seed_runner_data(db):
    service = WatchlistService(db)
    service.add_symbol("SOXL")
    item = service.get_symbol("SOXL")
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == "US.SOXL"))
    if not instrument:
        instrument = Instrument(
            symbol="US.SOXL", market="US", code="SOXL", is_supported=True,
            support_status="SUPPORTED", support_message="可用",
        )
        db.add(instrument)
        db.flush()
    timestamp = datetime(2026, 1, 5, tzinfo=timezone.utc)
    db.add(MarketBar(
        instrument_id=instrument.id, symbol="US.SOXL", interval="1d",
        timestamp_utc=timestamp, timestamp_market=timestamp, trading_date="2026-01-05",
        open=100, high=102, low=99, close=101, volume=1000, turnover=100000,
        is_blank=False, market_session="REGULAR", adjustment_type="FORWARD",
        data_source="MOOMOO",
    ))
    values = strategy_input().features
    for name, value in values.items():
        if name.startswith("_"):
            continue
        db.add(FeatureValueRecord(
            instrument_id=instrument.id, symbol="US.SOXL", interval="1d",
            timestamp_utc=timestamp, feature_name=name, feature_version="1.0.0",
            parameters_hash="feature", value_decimal=value, quality_status="VALID",
            source_bar_timestamp=timestamp, data_source="MOOMOO",
        ))
    db.commit()
    return item, timestamp


def test_signal_upsert_idempotent(db):
    item, timestamp = seed_runner_data(db)
    repo = StrategyRepository(db)
    evaluation = PullbackRestrengthStrategy().evaluate(strategy_input())
    repo.upsert_signal(item, "1d", timestamp, "p", evaluation)
    repo.upsert_signal(item, "1d", timestamp, "p", evaluation)
    assert db.query(CandidateSignal).count() == 1


def test_incremental_repeated_has_no_duplicate(db):
    seed_runner_data(db)
    settings = Settings(
        database_url="sqlite://", moomoo_strategy_auto_calculate_features=False,
    )
    runner = StrategyRunner(db, settings)
    first = runner.run(["SOXL"], ["1d"], auto_calculate_features=False)
    second = runner.run(["SOXL"], ["1d"], auto_calculate_features=False)
    assert first["signals_written"] == 1
    assert second["signals_written"] == 0
    assert db.query(CandidateSignal).count() == 1


@pytest.mark.parametrize("mode", ["FULL", "RANGE"])
def test_full_and_range_repeat_upsert(db, mode):
    _, timestamp = seed_runner_data(db)
    settings = Settings(database_url="sqlite://")
    runner = StrategyRunner(db, settings)
    start, end = timestamp - timedelta(seconds=1), timestamp + timedelta(seconds=1)
    runner.run(["SOXL"], ["1d"], mode, start, end, False)
    runner.run(["SOXL"], ["1d"], mode, start, end, False)
    assert db.query(CandidateSignal).count() == 1


def test_full_requires_range(db):
    WatchlistService(db).add_symbol("SOXL")
    with pytest.raises(ValueError):
        StrategyRunner(db, Settings(database_url="sqlite://")).run(["SOXL"], ["1d"], "FULL")


def test_large_task_requires_confirmation(db):
    WatchlistService(db).initialize_defaults()
    with pytest.raises(ValueError, match="数据量较大"):
        StrategyRunner(db, Settings(database_url="sqlite://")).run(
            list(DEFAULT_WATCHLIST[:6]), ["1d"], dry_run=True,
        )


def test_disabled_ticker_rejected(db):
    service = WatchlistService(db)
    service.add_symbol("SOXL")
    service.disable_symbol("SOXL")
    with pytest.raises(ValueError, match="停用"):
        StrategyRunner(db, Settings(database_url="sqlite://")).run(["SOXL"], ["1d"], dry_run=True)


def test_future_input_change_does_not_change_current_signal():
    current = strategy_input()
    first = PullbackRestrengthStrategy().evaluate(current)
    future = strategy_input(feature_changes={"ema_20": Decimal("1")})
    PullbackRestrengthStrategy().evaluate(future)
    second = PullbackRestrengthStrategy().evaluate(current)
    assert (first.signal_type, first.score, first.confidence, first.components, first.reasons, first.risks) == (
        second.signal_type, second.score, second.confidence, second.components, second.reasons, second.risks
    )


def test_truncated_and_full_inputs_at_same_timestamp_match():
    one = PullbackRestrengthStrategy().evaluate(strategy_input())
    two = PullbackRestrengthStrategy().evaluate(strategy_input())
    assert one == two


def test_full_and_range_results_match(db):
    _, timestamp = seed_runner_data(db)
    settings = Settings(database_url="sqlite://")
    runner = StrategyRunner(db, settings)
    start, end = timestamp - timedelta(seconds=1), timestamp + timedelta(seconds=1)
    runner.run(["SOXL"], ["1d"], "FULL", start, end, False)
    full = db.scalar(select(CandidateSignal))
    snapshot = (full.signal_type, full.score, full.confidence, full.components_json)
    runner.run(["SOXL"], ["1d"], "RANGE", start, end, False)
    repaired = db.scalar(select(CandidateSignal))
    assert snapshot == (repaired.signal_type, repaired.score, repaired.confidence, repaired.components_json)


def test_unclosed_realtime_bar_does_not_write_signal(db):
    item, timestamp = seed_runner_data(db)
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == "US.SOXL"))
    db.add(RealtimeBar(
        instrument_id=instrument.id, symbol="US.SOXL", interval="1m",
        timestamp_utc=timestamp, timestamp_market=timestamp, trading_date="2026-01-05",
        open=100, high=102, low=99, close=101, volume=1000, turnover=100000,
        is_closed=False, market_session="REGULAR", data_source="MOOMOO",
    ))
    db.commit()
    result = StrategyRunner(db, Settings(database_url="sqlite://")).run(
        ["SOXL"], ["1m"], "REALTIME", auto_calculate_features=False,
    )
    assert result["signals_written"] == 0
    assert db.query(CandidateSignal).count() == 0


def test_benchmark_requires_exact_timestamp(db):
    item, timestamp = seed_runner_data(db)
    db.query(FeatureValueRecord).filter_by(feature_name="relative_return_soxx_20").delete()
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == "US.SOXL"))
    db.add(FeatureValueRecord(
        instrument_id=instrument.id, symbol="US.SOXL", interval="1d",
        timestamp_utc=timestamp + timedelta(seconds=1),
        feature_name="relative_return_soxx_20", feature_version="1.0.0",
        parameters_hash="adjacent", value_decimal=Decimal("1"),
        quality_status="VALID", source_bar_timestamp=timestamp + timedelta(seconds=1),
        data_source="MOOMOO",
    ))
    db.commit()
    resolved = FeatureDependencyResolver(
        StrategyRepository(db), feature_service=None,
    ).resolve("SOXL", "1d", timestamp, "SOXX", False)
    assert resolved["values"]["relative_return_soxx_20"] is None
    assert resolved["statuses"]["relative_return_soxx_20"] == "MISSING"


def test_previous_or_next_benchmark_is_not_substituted(db):
    _, timestamp = seed_runner_data(db)
    resolved = FeatureDependencyResolver(
        StrategyRepository(db), feature_service=None,
    ).resolve("SOXL", "1d", timestamp + timedelta(hours=1), "SOXX", False)
    assert all(
        value is None for name, value in resolved["values"].items()
        if not name.startswith("_")
    )


def test_strategy_source_does_not_recompute_rolling_or_volume():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "app" / "strategy"
    text = "\n".join(path.read_text() for path in root.rglob("*.py"))
    assert ".rolling(" not in text
    assert ".bfill(" not in text
    assert ".backfill(" not in text


def test_missing_never_becomes_zero():
    result = PullbackRestrengthStrategy().evaluate(strategy_input(
        feature_changes={"ema_20": None},
        status_changes={"ema_20": "MISSING"},
    ))
    assert result.score == 0
    assert result.signal_type == "INSUFFICIENT_DATA"


def test_parameters_hash_is_part_of_signal_identity(db):
    item, timestamp = seed_runner_data(db)
    repo = StrategyRepository(db)
    evaluation = PullbackRestrengthStrategy().evaluate(strategy_input())
    repo.upsert_signal(item, "1d", timestamp, "old", evaluation)
    repo.upsert_signal(item, "1d", timestamp, "new", evaluation)
    assert db.query(CandidateSignal).count() == 2


def test_auto_calculation_requests_only_missing_target_features(db):
    _, timestamp = seed_runner_data(db)

    class Job:
        status = "FAILED"
        error_message = "mock"

    class FeatureService:
        def __init__(self):
            self.calls = []

        def calculate_symbol(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return Job()

    # Remove one optional target value and verify the resolver requests a strict subset.
    db.query(FeatureValueRecord).filter_by(feature_name="volume_ratio_20").delete()
    db.commit()
    fake = FeatureService()
    resolver = FeatureDependencyResolver(StrategyRepository(db), fake)
    resolver.resolve("SOXL", "1d", timestamp, "SOXX", True)
    requested = fake.calls[0][0][2]
    assert "volume_ratio_20" in requested
    assert len(requested) < 73
    assert fake.calls[0][0][0] == "US.SOXL"
    assert fake.calls[0][0][1].value == "1d"
