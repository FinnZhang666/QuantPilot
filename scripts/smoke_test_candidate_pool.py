"""Offline Sprint 09 smoke test; does not connect OpenD or trading APIs."""

from datetime import datetime, timezone

from app.candidate_pool.filters import evaluate_filters
from app.candidate_pool.ranking import CandidateRanker
from app.candidate_pool.service import load_candidate_config
from app.market_regime.scoring import MarketRegimeScorer
from app.market_regime.service import load_config


def main():
    now = datetime.now(timezone.utc)
    snapshots = {
        "QQQ": {
            "_timestamp": now, "close_vs_ema20_pct": 2,
            "ema20_vs_ema60_pct": 2, "ema20_slope_5": .2,
            "return_5": 2, "rsi_14": 60, "atr_pct_14": 2,
        },
        "SOXX": {"return_5": 1},
        "SOXS": {"return_5": -1},
    }
    regime = MarketRegimeScorer(load_config("config/market_regime_v1.yaml")).score(
        snapshots, now,
    )
    candidate_config = load_candidate_config()
    long_features = {
        "close_vs_ema20_pct": 2, "ema20_vs_ema60_pct": 2, "ema20_slope_5": .2,
        "breakout_high_20_pct": -1, "distance_from_low_20_pct": 10,
        "relative_return_qqq_20": 3, "volume_ratio_20": 1.5,
        "return_1": 1, "atr_pct_14": 3,
    }
    short_features = dict(long_features)
    short_features.update({
        "close_vs_ema20_pct": -2, "ema20_vs_ema60_pct": -2,
        "ema20_slope_5": -.2, "breakout_high_20_pct": -10,
        "distance_from_low_20_pct": 1, "relative_return_qqq_20": -3,
        "return_1": -1,
    })
    ranker = CandidateRanker(60, 5)
    long_result = ranker.rank_one(
        evaluate_filters(long_features, candidate_config, True), None,
    )
    short_result = ranker.rank_one(
        evaluate_filters(short_features, candidate_config, True), None,
    )
    assert regime.regime in {"STRONG_BULL", "BULL"}
    assert long_result["direction"] == "LONG"
    assert short_result["direction"] == "SHORT"
    print("Sprint 09离线Smoke Test通过")
    print("Market Regime：%s，LONG/SHORT Bias：%s/%s" % (
        regime.regime, regime.long_bias, regime.short_bias,
    ))
    print("隔离样本方向：LONG=%s，SHORT=%s" % (
        long_result["final_score"], short_result["final_score"],
    ))
    print("未连接OpenD，未调用LLM，未调用任何订单接口。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
