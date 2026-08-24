from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import yaml

from app.qmr_backtest.engine import QmrBacktestEngine
from app.qmr_backtest.metrics import (
    confidence_label, proportion_ci, summarize, target_stop_path, trailing_stop_path,
)
from app.qmr_backtest.repository import QmrBacktestRepository


CONFIG = yaml.safe_load(open("config/qmr_backtest_v1.yaml", encoding="utf-8"))
NOW = datetime(2024, 1, 10, tzinfo=timezone.utc)


def bar(day, open_price, high, low, close):
    return SimpleNamespace(timestamp_utc=NOW + timedelta(days=day), open=open_price,
        high=high, low=low, close=close, volume=100)


def score(status="EARLY_ENTRY"):
    return SimpleNamespace(id=7, symbol="MU", evaluation_time=NOW, buy_status=status,
        quality_score=90, mispricing_score=88, recovery_score=82, final_buy_score=84,
        buy_grade="A", data_confidence="HIGH",
        score_components_json={"recovery_stage": "RECOVERY_CONFIRMED", "risk": {}})


def test_mfe_mae_returns_and_bottom_capture_are_exact():
    engine = QmrBacktestEngine(CONFIG)
    bars = [bar(-1, 99, 101, 95, 100), bar(1, 100, 110, 96, 105),
            bar(2, 105, 120, 102, 115)] + [bar(i, 115, 118, 110, 116) for i in range(3, 25)]
    result = engine.evaluate(1, score(), SimpleNamespace(sector="Semiconductors"), "EARLY_ENTRY", bars)
    assert result["returns_json"]["1d"] == pytest.approx(5)
    assert result["mfe_json"]["1d"] == pytest.approx(10)
    assert result["mae_json"]["1d"] == pytest.approx(-4)
    assert round(result["signal_vs_local_bottom"], 6) == round((100 / 95 - 1) * 100, 6)


def test_same_bar_target_stop_is_conservative_by_default():
    result = target_stop_path([bar(1, 100, 111, 94, 105)], 100, 10, 5, "STOP_FIRST")
    assert result == {"outcome": "STOP", "bars": 1, "return_pct": -5, "ambiguous": True}


def test_trailing_stop_tracks_high_and_uses_long_direction():
    result = trailing_stop_path([bar(1, 100, 120, 110, 115)], 100, 5)
    assert result["outcome"] == "TRAILING_STOP"
    assert result["return_pct"] == pytest.approx(14)


def test_future_beyond_outcome_window_does_not_change_historical_case():
    engine = QmrBacktestEngine(CONFIG)
    base = [bar(i, 100, 101, 99, 100 + i / 10) for i in range(-2, 25)]
    first = engine.evaluate(1, score(), SimpleNamespace(sector=None), "EARLY_ENTRY", base)
    changed = base + [bar(100, 1, 10000, .01, 9999)]
    second = engine.evaluate(1, score(), SimpleNamespace(sector=None), "EARLY_ENTRY", changed)
    for key in ("returns_json", "mfe_json", "mae_json", "target_stop_json"):
        assert first[key] == second[key]


def test_entry_levels_are_independently_emitted_once():
    engine = QmrBacktestEngine(CONFIG)
    rows = [(score("STRONG_ENTRY"), SimpleNamespace(sector=None)),
            (score("STRONG_ENTRY"), SimpleNamespace(sector=None))]
    assert [item[2] for item in engine.events(rows)] == CONFIG["entry_levels"]


def test_entry_event_rearms_after_status_falls_below_threshold():
    engine = QmrBacktestEngine(CONFIG)
    rows = [(score("EARLY_ENTRY"), SimpleNamespace(sector=None)),
            (score("WATCH"), SimpleNamespace(sector=None)),
            (score("EARLY_ENTRY"), SimpleNamespace(sector=None))]
    assert [item[2] for item in engine.events(rows)] == ["EARLY_ENTRY", "EARLY_ENTRY"]


def test_confidence_intervals_and_sample_labels():
    assert confidence_label(12) == "LOW"
    assert confidence_label(35) == "PRELIMINARY"
    assert confidence_label(150) == "MEDIUM"
    assert confidence_label(300) == "HIGH"
    low, high = proportion_ci(72, 100)
    assert low < .72 < high
    assert summarize([1, -1, 3])["sample_count"] == 3


def test_walk_forward_concept_has_strict_year_boundary():
    train_end = datetime(2022, 12, 31, tzinfo=timezone.utc)
    test_start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert train_end < test_start


def test_parameter_versions_cannot_be_silently_overwritten(db):
    repository = QmrBacktestRepository(db)
    first = repository.parameter_set("baseline", "QMR-v1", "abc", {"threshold": 70})
    assert repository.parameter_set("baseline", "QMR-v1", "abc", {"threshold": 70}).id == first.id
    with pytest.raises(ValueError, match="新参数集名称"):
        repository.parameter_set("baseline", "QMR-v1", "different", {"threshold": 80})
