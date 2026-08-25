from datetime import datetime, timedelta, timezone

from app.dashboard.analysis_presentation import (
    freshness, localized_view, risk_reward, score_state, valuation_view,
)


def test_human_score_states_are_stable():
    assert score_state(85) == "VERY_STRONG"
    assert score_state(65) == "STRONG"
    assert score_state(50) == "NEUTRAL"
    assert score_state(35) == "WEAK"
    assert score_state(10) == "VERY_WEAK"
    assert score_state(None) == "UNAVAILABLE"


def test_valuation_uses_persisted_peer_result_and_value_trap():
    qmr = {"score_components": {"mispricing": {
        "peer": {"available": True, "score": 72, "peer_method": "INDUSTRY", "peer_count": 18},
        "value_trap": {"deduction": 12, "flags": ["persistent_negative_fcf"]},
    }}}
    value = valuation_view(qmr)
    assert value["state"] == "LOW_VALUATION"
    assert value["peer_method"] == "INDUSTRY"
    assert value["peer_count"] == 18
    assert value["value_trap_state"] == "VALUE_TRAP_PRESENT"


def test_missing_peer_comparison_is_not_fabricated():
    value = valuation_view({"score_components": {"mispricing": {}}})
    assert value["available"] is False
    assert value["score"] is None
    assert value["state"] == "UNAVAILABLE"


def test_risk_reward_requires_reliable_plan_prices():
    assert risk_reward(100, None, [120])["status"] == "UNAVAILABLE"
    assert risk_reward(100, 95, [])["status"] == "UNAVAILABLE"
    assert risk_reward(100, 95, [115]) == {
        "status": "AVAILABLE", "ratio": 3.0, "entry": "100",
        "invalidation": "95", "target": "115",
    }


def test_freshness_exposes_delayed_and_stale_data():
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    assert freshness(now - timedelta(minutes=5), now)["status"] == "FRESH"
    assert freshness(now - timedelta(hours=3), now)["status"] == "DELAYED"
    assert freshness(now - timedelta(days=2), now)["status"] == "STALE"


def test_dashboard_and_agent_share_bilingual_presentation_dictionary():
    payload = {
        "analysis_model": "LEVERAGED_ETF_ANALYSIS",
        "instrument": {"asset_type": "LEVERAGED_ETF"},
        "quality_score": 82,
        "valuation": {"state": "LOW_VALUATION", "value_trap_state": "VALUE_TRAP_LOW"},
        "market_context": {"global": {"global_score": 55}, "sector": {"sector_score": 38}},
        "freshness": {"status": "FRESH"},
    }
    zh = localized_view(payload, "zh-CN")
    en = localized_view(payload, "en-US")
    assert zh["analysis_model"] == "杠杆ETF交易载体分析"
    assert zh["quality"] == "很强" and zh["sector"] == "偏弱"
    assert en["asset_type"] == "Leveraged ETF"
    assert "估值" in zh["info"]["valuation"]
