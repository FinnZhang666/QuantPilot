from types import SimpleNamespace

import pytest
import yaml

from app.qmr_exit.backtest import comparison_paths, exit_engine_path
from app.qmr_exit.scoring import evaluate_exit, evaluate_money_flow
from app.qmr_exit.formatter import qmr_exit_message


def flow(super_net=0, large=0, medium=0, small=0, turnover=1000000):
    return {"super_large_net": super_net, "large_net": large, "medium_net": medium,
            "small_net": small, "total_turnover": turnover,
            "super_large_inflow": max(super_net, 0), "super_large_outflow": max(-super_net, 0),
            "large_inflow": max(large, 0), "large_outflow": max(-large, 0),
            "medium_inflow": max(medium, 0), "medium_outflow": max(-medium, 0),
            "small_inflow": max(small, 0), "small_outflow": max(-small, 0),
            "total_inflow": sum(max(x, 0) for x in (super_net, large, medium, small)),
            "total_outflow": sum(max(-x, 0) for x in (super_net, large, medium, small)),
            "total_net": super_net + large + medium + small}


def bars(values, volume=1000):
    return [SimpleNamespace(open=value * .995, high=value * 1.01, low=value * .99,
                            close=value, volume=volume) for value in values]


@pytest.fixture
def config():
    with open("config/qmr_exit_v1.yaml", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


@pytest.mark.parametrize("raw,price,expected", [
    (flow(5000, 4000, 1000, -6000), {"higher_low": True}, "ACCUMULATION"),
    (flow(-5000, -4000, 1000, 6000), {"high_stall": True}, "DISTRIBUTION"),
    (flow(5000, 4000, 2000, 3000), {}, "BROAD_BUYING"),
    (flow(-5000, -4000, -2000, -3000), {}, "BROAD_SELLING"),
    (flow(-500, -300, 0, -7000), {"rejected_lower": True}, "POSSIBLE_ABSORPTION"),
    (flow(100, -100, 0, 100), {}, "NEUTRAL"),
])
def test_money_flow_regimes(raw, price, expected, config):
    result = evaluate_money_flow(raw, price, config=config["money_flow"])
    assert result["regime"] == expected


def test_money_flow_missing_and_zero_turnover(config):
    assert evaluate_money_flow(None)["data_available"] is False
    result = evaluate_money_flow(flow(turnover=0), config=config["money_flow"])
    assert result["data_available"] is False
    assert result["error"] == "total_turnover_zero"


def test_money_flow_extreme_values_are_bounded(config):
    result = evaluate_money_flow(flow(10**15, 10**15, 10**15, -10**15),
                                 {"higher_low": True}, config=config["money_flow"])
    assert 0 <= result["accumulation_score"] <= 100
    assert 0 <= result["money_flow_score"] <= 100


def test_incomplete_session_data_is_unavailable(config):
    raw = flow(); raw.pop("large_net")
    assert evaluate_money_flow(raw, config=config["money_flow"])["data_available"] is False


def test_continuous_rise_stays_hold(config):
    daily = bars([100 + index for index in range(30)])
    result = evaluate_exit(100, 130, 129, {"1d": daily, "60m": daily, "30m": daily},
        {}, [], {}, {"data_available": False, "money_flow_score": None, "regime": "NEUTRAL"}, config)
    assert result["state"] == "HOLD"


def test_intraday_cross_does_not_force_exit_when_daily_is_healthy(config):
    daily = bars([100 + index for index in range(30)])
    weak = bars([130 - index * .5 for index in range(30)])
    result = evaluate_exit(100, 130, 125, {"1d": daily, "60m": daily, "30m": weak},
        {}, [], {}, {"data_available": False, "money_flow_score": None, "regime": "NEUTRAL"}, config)
    assert result["state"] != "EXIT"


def test_profit_giveback_enters_protection(config):
    daily = bars([100 + index for index in range(25)] + [122, 117, 112, 110, 108])
    result = evaluate_exit(100, 125, 108, {"1d": daily, "60m": daily, "30m": daily},
        {}, [], {}, {"data_available": False, "money_flow_score": None, "regime": "NEUTRAL"}, config)
    assert result["state"] in {"PROTECT", "REDUCE", "EXIT"}
    assert "profit_giveback_reduce" in result["reasons"]


def test_flow_missing_does_not_become_zero_risk(config):
    daily = bars([100 + index * .1 for index in range(30)])
    result = evaluate_exit(100, 104, 103, {"1d": daily, "60m": [], "30m": []}, {}, [], {},
        {"data_available": False, "money_flow_score": None, "regime": "NEUTRAL"}, config)
    assert result["components"]["capital_flow"] is None
    assert result["confidence"] < 100


def test_effective_support_break_is_hard_exit(config):
    daily = bars([120 - index * .6 for index in range(30)])
    daily[-1].close = daily[-1].low = 80
    result = evaluate_exit(110, 125, 80, {"1d": daily, "60m": daily, "30m": daily}, {}, [], {},
        {"data_available": False, "money_flow_score": None, "regime": "BROAD_SELLING"}, config)
    assert result["state"] == "EXIT"
    assert result["hard_exit_reason"]


def test_backtest_uses_prefixes_and_reports_captured_mfe(config):
    path = bars([101, 103, 106, 110, 115, 120, 118, 114, 109, 105] + [104] * 15)
    result = exit_engine_path(path, 100, config)
    assert result["peak_return"] >= result["realized_return"]
    assert "captured_mfe_ratio" in result
    comparison = comparison_paths(path, 100, config)
    assert set(comparison) == {"fixed_5d", "fixed_10d", "target_10pct",
                               "traditional_target_stop", "qmr_exit_engine"}


def test_sector_rotation_alone_does_not_force_exit(config):
    daily = bars([100 + index * .2 for index in range(30)])
    current = bars([100 + index * .1 for index in range(30)])
    strong = bars([100 + index for index in range(30)])
    result = evaluate_exit(100, 107, 106, {"1d": daily, "60m": daily, "30m": daily}, {}, current,
        {"CURRENT": current, "STRONG": strong}, {"data_available": False, "money_flow_score": None,
        "regime": "NEUTRAL"}, config)
    assert result["state"] != "EXIT"


def test_exit_telegram_formatter_uses_proxy_language_not_certain_institution_claim():
    evaluation = SimpleNamespace(symbol="APP", state="REDUCE", reduce_ratio=.333333,
        exit_risk_score=68, current_price=120, entry_price=100, highest_price=130,
        current_return=20, max_return=30, profit_giveback=10, capital_flow_risk=75,
        trend_risk=60, relative_strength_risk=55, sector_rotation_risk=40,
        profit_protection_risk=70, exhaustion_risk=45, money_flow_regime="DISTRIBUTION",
        reasons_json=["money_flow_possible_distribution"])
    text = qmr_exit_message(evaluation).text
    assert "疑似派发" in text and "减仓 33%" in text
    assert "主力正在" not in text and "真实交易" in text
