from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import yaml

from app.buy_score.scoring import apply_hysteresis, calculate
from app.buy_score.service import BuyScoreService
from app.buy_score.repository import BuyScoreRepository
from app.core.config import Settings
from app.database.models import MispricingScoreRecord, QmrCandidateRecord, QualityScoreRecord, RecoveryScoreRecord, UniverseInstrument


CONFIG = yaml.safe_load(open("config/buy_score_v1.yaml", encoding="utf-8"))
NOW = datetime(2026, 8, 24, 15, 0, tzinfo=timezone.utc)


def inputs(recovery=90, stage="RECOVERY_CONFIRMED", fundamental="LOW", price=100,
           signal_price=98, confidence="HIGH", sector=80, market=70):
    return {
        "quality_score": 90, "mispricing_score": 90, "recovery_score": recovery,
        "sector_score": sector, "market_score": market, "etf_importance_score": 80,
        "fundamental_risk": fundamental, "recovery_stage": stage,
        "market_state": "MARKET_RECOVERY", "data_confidence": confidence,
        "current_price": price, "recovery_signal_price": signal_price,
        "volatility": {"atr_pct": 3, "realized_volatility": .3,
                       "intraday_range_pct": 4, "recent_max_drawdown_pct": 15},
    }


def test_case_a_high_quality_mispricing_low_recovery_is_watch():
    result = calculate(inputs(recovery=30, stage="PANIC"), CONFIG)
    assert result["buy_status"] == "WATCH"


def test_case_b_high_quality_mispricing_recovery_is_confirmed():
    result = calculate(inputs(), CONFIG)
    assert result["buy_status"] == "CONFIRMED_ENTRY"
    assert result["final_buy_score"] >= 80


def test_case_c_high_fundamental_risk_is_hard_reject_zero():
    result = calculate(inputs(fundamental="HIGH"), CONFIG)
    assert result["buy_status"] == "REJECT"
    assert result["final_buy_score"] == 0


def test_case_d_extreme_chase_risk_caps_status_at_watch():
    result = calculate(inputs(price=120, signal_price=100), CONFIG)
    assert result["chase_risk_level"] == "HIGH"
    assert result["entry_attractiveness"] == "LOW"
    assert result["buy_status"] == "WATCH"
    assert result["risk_penalty"] > 0


def test_case_e_hysteresis_prevents_threshold_flapping():
    previous = SimpleNamespace(buy_status="CONFIRMED_ENTRY", evaluation_time=NOW,
                               cooldown_until=None)
    assert apply_hysteresis("EARLY_ENTRY", 78, previous, NOW + timedelta(minutes=15), CONFIG) == "CONFIRMED_ENTRY"
    assert apply_hysteresis("EARLY_ENTRY", 74, previous, NOW + timedelta(minutes=15), CONFIG) == "EARLY_ENTRY"
    assert apply_hysteresis("STRONG_ENTRY", 95, previous, NOW + timedelta(minutes=5), CONFIG) == "CONFIRMED_ENTRY"


def test_market_panic_immediately_caps_existing_confirmed_entry():
    previous = SimpleNamespace(buy_status="CONFIRMED_ENTRY", final_buy_score=85,
                               evaluation_time=NOW - timedelta(minutes=30), cooldown_until=None)
    result = calculate(inputs(recovery=30, stage="PANIC"), CONFIG, previous, NOW)
    assert result["buy_status"] == "WATCH"


def test_failed_recovery_sets_wait_and_cooldown():
    result = calculate(inputs(stage="FAILED_RECOVERY"), CONFIG, evaluation_time=NOW)
    assert result["buy_status"] == "WAIT"
    assert result["cooldown_until"] == NOW + timedelta(minutes=60)
    previous = SimpleNamespace(buy_status="CONFIRMED_ENTRY", evaluation_time=NOW - timedelta(minutes=2),
                               cooldown_until=None)
    repeated = calculate(inputs(stage="FAILED_RECOVERY"), CONFIG, previous, NOW)
    assert repeated["buy_status"] == "WAIT"


def test_case_f_mu_mapping_returns_mull_without_trade_side_effect(db):
    service = BuyScoreService(db, Settings())
    mappings = service.mappings("MU")
    assert any(item["leveraged_symbol"] == "MULL" and item["direction"] == "LONG" for item in mappings)
    assert not hasattr(service, "place_order")


def test_first_discovery_prices_are_monotonic_and_preserved():
    first = BuyScoreService._first_prices(None, "CONFIRMED_ENTRY", 10.8)
    assert first["first_watch_price"] == 10.8
    assert first["first_early_entry_price"] == 10.8
    assert first["first_confirmed_entry_price"] == 10.8
    previous = SimpleNamespace(**first)
    later = BuyScoreService._first_prices(previous, "STRONG_ENTRY", 11.0)
    assert later["first_confirmed_entry_price"] == 10.8
    assert later["first_strong_entry_price"] == 11.0


def test_missing_volatility_is_penalized_not_treated_as_safe():
    data = inputs()
    data["volatility"] = {}
    result = calculate(data, CONFIG)
    assert result["components"]["risk"]["volatility"]["penalty"] > 0


def score_values(symbol, timestamp, score):
    return {"qmr_candidate_id": 1, "recovery_score_id": 1, "symbol": symbol,
        "evaluation_time": timestamp, "quality_score": 80, "mispricing_score": 85,
        "recovery_score": 80, "sector_score": 75, "market_score": 70,
        "etf_importance_score": 80, "raw_buy_score": score, "risk_penalty": 0,
        "final_buy_score": score, "buy_grade": "A", "buy_status": "CONFIRMED_ENTRY",
        "recommended_action": "CONFIRMED_ENTRY_CANDIDATE", "entry_reference_price": 10,
        "entry_zone_low": 9.8, "entry_zone_high": 10.2, "first_watch_price": 10,
        "first_early_entry_price": 10, "first_confirmed_entry_price": 10,
        "first_strong_entry_price": None, "rank_current": None, "rank_previous": None,
        "rank_change": None, "chase_risk_score": 0, "chase_risk_level": "LOW",
        "entry_attractiveness": "HIGH", "recommended_position_confidence": "HIGH",
        "holding_profile": "UNKNOWN", "cooldown_until": None, "data_confidence": "HIGH",
        "model_version": "buy-score-v1", "score_components_json": {}}


def test_ranking_is_idempotent_and_tracks_rank_change(db):
    repository = BuyScoreRepository(db)
    a1, created = repository.save(score_values("AAA", NOW, 90))
    repository.save(score_values("BBB", NOW, 80))
    duplicate, created_again = repository.save(score_values("AAA", NOW, 90))
    assert created is True and created_again is False and duplicate.id == a1.id
    first = repository.rank(NOW, "buy-score-v1")
    assert [row.symbol for row in first] == ["AAA", "BBB"]
    later = NOW + timedelta(minutes=5)
    repository.save(score_values("AAA", later, 75))
    repository.save(score_values("BBB", later, 95))
    second = repository.rank(later, "buy-score-v1")
    assert [row.symbol for row in second] == ["BBB", "AAA"]
    assert second[0].rank_previous == 2 and second[0].rank_change == 1


def test_service_reads_qmr_watch_and_matching_recovery_then_ranks(db):
    universe = UniverseInstrument(symbol="FLOW", market="US", status="ACTIVE")
    db.add(universe); db.flush()
    quality = QualityScoreRecord(universe_id=universe.id, symbol="FLOW", evaluation_time=NOW,
        quality_score=88, score_components_json={}, data_sources_json=[], data_confidence="HIGH",
        data_coverage=1, model_version="qmr-v1")
    mispricing = MispricingScoreRecord(universe_id=universe.id, symbol="FLOW", evaluation_time=NOW,
        mispricing_score=90, fundamental_risk="LOW", event_risk="A", news_confidence="HIGH",
        score_components_json={}, data_sources_json=[], data_confidence="HIGH", model_version="qmr-v1")
    db.add_all([quality, mispricing]); db.flush()
    qmr = QmrCandidateRecord(universe_id=universe.id, quality_score_id=quality.id,
        mispricing_score_id=mispricing.id, symbol="FLOW", evaluation_time=NOW,
        quality_score=88, mispricing_score=90, combined_score=89, fundamental_risk="LOW",
        event_risk="A", candidate_status="WATCH",
        score_components_json={"quality": {"etf_importance": {"score": 12, "max": 15}},
                               "mispricing": {"returns": {"5D": -.18}}},
        data_sources_json=[], data_confidence="HIGH", model_version="qmr-v1")
    db.add(qmr); db.flush()
    recovery = RecoveryScoreRecord(qmr_candidate_id=qmr.id, symbol="FLOW", evaluation_time=NOW,
        price=100, session_low=95, session_high=102, low_recovery_pct=.052,
        stabilization_score=85, capital_flow_score=82, technical_score=80,
        sector_recovery_score=80, market_recovery_score=75, global_context_score=None,
        recovery_score=84, recovery_stage="RECOVERY_CONFIRMED", entry_status="CONFIRMED_ENTRY",
        market_state="MARKET_RECOVERY", trading_session="REGULAR", capital_flow_data="PARTIAL",
        score_components_json={}, data_sources_json=[], data_confidence="HIGH",
        model_version="recovery-v1", failure_reason=None)
    db.add(recovery); db.commit()
    service = BuyScoreService(db, Settings())
    result = service.run(NOW + timedelta(minutes=1), dry_run=False)
    assert result["scanned"] == 1 and result["created"] == 1 and result["ranked"] == 1
    assert result["items"][0]["symbol"] == "FLOW"
    assert result["items"][0]["rank_current"] == 1
