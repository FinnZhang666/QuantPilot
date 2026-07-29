from datetime import datetime, timezone

import pytest

from app.candidate_pool.filters import evaluate_filters
from app.candidate_pool.models import FilterResult, UniverseSymbol
from app.candidate_pool.ranking import CandidateRanker
from app.candidate_pool.universe import CombinedUniverseProvider
from app.market_regime.scoring import MarketRegimeScorer
from app.market_regime.service import load_config
from app.candidate_pool.service import load_candidate_config


NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def regime_config():
    return load_config("config/market_regime_v1.yaml")


def snapshot(close=2, spread=2, slope=.1, ret=2, rsi=60, atr=2, soxx_ret=1, soxs_ret=-1):
    return {
        "QQQ": {
            "close_vs_ema20_pct": close, "ema20_vs_ema60_pct": spread,
            "ema20_slope_5": slope, "return_5": ret, "rsi_14": rsi,
            "atr_pct_14": atr, "_timestamp": NOW,
        },
        "SOXX": {"return_5": soxx_ret},
        "SOXS": {"return_5": soxs_ret},
    }


@pytest.mark.parametrize("expected,values", [
    ("STRONG_BULL", snapshot()),
    ("BULL", snapshot(atr=10, soxx_ret=-1)),
    ("NEUTRAL", snapshot(close=1, spread=-1, slope=.1, ret=-1, rsi=40)),
    ("BEAR", snapshot(close=-1, spread=-1, slope=-.1, ret=-1, rsi=40, atr=2, soxx_ret=-1)),
    ("STRONG_BEAR", snapshot(close=-1, spread=-1, slope=-.1, ret=-1, rsi=30, atr=10, soxx_ret=1, soxs_ret=2)),
])
def test_regime_states(expected, values):
    assert MarketRegimeScorer(regime_config()).score(values, NOW).regime == expected


def test_regime_unknown_and_snapshot_complete():
    result = MarketRegimeScorer(regime_config()).score({"QQQ": {}}, NOW)
    assert result.regime == "UNKNOWN" and not result.data_sufficient
    assert result.features == {"QQQ": {}} and result.config_version == "1.0.0"


def test_regime_uses_multiple_indicators_and_soxs_risk():
    safe = MarketRegimeScorer(regime_config()).score(snapshot(soxs_ret=-1), NOW)
    risky = MarketRegimeScorer(regime_config()).score(snapshot(soxs_ret=3), NOW)
    assert risky.risk_score < safe.risk_score
    assert risky.short_bias >= safe.short_bias


def test_bull_does_not_zero_short_and_bear_does_not_zero_long():
    scorer = MarketRegimeScorer(regime_config())
    bull = scorer.score(snapshot(), NOW)
    bear = scorer.score(snapshot(close=-1, spread=-1, slope=-1, ret=-1, rsi=35), NOW)
    assert bull.short_bias > 0 and bear.long_bias > 0


def candidate_features(**overrides):
    values = {
        "close_vs_ema20_pct": 2, "ema20_vs_ema60_pct": 2,
        "ema20_slope_5": .2, "breakout_high_20_pct": -1,
        "distance_from_low_20_pct": 10, "relative_return_qqq_20": 3,
        "volume_ratio_20": 1.5, "return_1": 1, "atr_pct_14": 3,
    }
    values.update(overrides)
    return values


def test_candidate_config_parses():
    config = load_candidate_config()
    assert config["version"] == "1.0.0" and config["weights"]["trend"] == 25


def test_long_candidate_filters():
    filters = evaluate_filters(candidate_features(), load_candidate_config(), True)
    result = CandidateRanker(60, 5).rank_one(filters, None)
    assert result["direction"] == "LONG" and result["long_score"] > result["short_score"]


def test_short_candidate_filters():
    features = candidate_features(
        close_vs_ema20_pct=-2, ema20_vs_ema60_pct=-2, ema20_slope_5=-.2,
        breakout_high_20_pct=-10, distance_from_low_20_pct=1,
        relative_return_qqq_20=-3, return_1=-1,
    )
    result = CandidateRanker(60, 5).rank_one(
        evaluate_filters(features, load_candidate_config(), True), None,
    )
    assert result["direction"] == "SHORT" and result["short_score"] > result["long_score"]


def test_both_candidate():
    filters = [
        FilterResult("mixed", True, 65, 63, ["双向结构"], [], True, {}),
    ]
    result = CandidateRanker(60, 5).rank_one(filters, None)
    assert result["direction"] == "BOTH"


def test_below_threshold_not_candidate():
    result = CandidateRanker(60, 5).rank_one([
        FilterResult("weak", True, 20, 20, [], [], True, {}),
    ], None)
    assert result["direction"] is None


def test_watchlist_is_priority_not_automatic_pass():
    result = CandidateRanker(60, 5).rank_one(
        evaluate_filters({}, load_candidate_config(), True), None,
    )
    assert result["direction"] is None and not result["data_sufficient"]


def test_unknown_regime_has_no_adjustment():
    filters = [FilterResult("base", True, 60, 60, [], [], True, {})]
    result = CandidateRanker(60, 5).rank_one(filters, None)
    assert result["regime_adjustment"] == {"long": 0, "short": 0}


def test_regime_adjustment_preserves_opposite_direction():
    regime = type("Regime", (), {"regime": "STRONG_BULL"})()
    result = CandidateRanker(40, 20).rank_one([
        FilterResult("base", True, 45, 45, [], [], True, {}),
    ], regime)
    assert result["short_score"] == 40 and result["long_score"] == 55


def test_stable_sort_contract():
    rows = [("ZZZ", 70), ("AAA", 70), ("BBB", 80)]
    assert sorted(rows, key=lambda row: (-row[1], row[0])) == [
        ("BBB", 80), ("AAA", 70), ("ZZZ", 70),
    ]


class Provider:
    def __init__(self, rows):
        self.rows = rows

    def get_symbols(self):
        return self.rows


def test_universe_multi_source_merge():
    combined = CombinedUniverseProvider([
        Provider([UniverseSymbol("SOXL", source="WATCHLIST")]),
        Provider([UniverseSymbol("SOXL", source="SYSTEM"), UniverseSymbol("QQQ", source="SYSTEM")]),
    ]).get_symbols()
    assert len(combined) == 2
    soxl = next(row for row in combined if row.symbol == "SOXL")
    assert soxl.source == "SYSTEM,WATCHLIST"
