from datetime import datetime, timedelta, timezone

from app.database.models import (
    MarketContextSnapshot, SectorContextSnapshot, UniverseInstrument,
    UniverseMembership,
)
from app.market_context.gating import entry_gate, exit_context_adjustment
from app.market_context.repository import MarketContextRepository
from app.market_context.scoring import global_score, sector_score
from app.market_context.validation import compare_context_variants
from app.qmr.repository import QmrRepository


NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)


def context_config():
    return {
        "assets": {"SPY": {"weight": .6, "inverse": False},
                   "VIX": {"weight": .4, "inverse": True}},
        "horizons": {1: .1, 3: .15, 5: .25, 10: .25, 20: .25},
        "states": {"risk_on": 70, "neutral": 50, "caution": 35},
        "minimum_coverage": .5,
    }


def gate_config():
    return {"global_block_below": 35, "global_probe_below": 50,
            "sector_block_below": 30, "sector_probe_below": 45,
            "multipliers": {"global": {"RISK_ON": 1, "NEUTRAL": .75,
                                         "CAUTION": .25, "RISK_OFF": 0},
                            "sector": {"STRONG": 1, "POSITIVE": .85,
                                       "NEUTRAL": .65, "WEAK": .25,
                                       "VERY_WEAK": 0}}}


def test_global_context_scores_cross_assets_and_missing_data():
    rising = [100 + value for value in range(30)]
    falling = [130 - value for value in range(30)]
    value = global_score({"SPY": rising, "VIX": falling}, context_config())
    assert value["global_state"] == "RISK_ON"
    assert value["coverage"] == 1
    missing = global_score({}, context_config())
    assert missing["data_sufficient"] is False
    assert missing["asset_scores"]["SPY"]["data_available"] is False


def test_sector_context_relative_strength_and_rotation():
    value = sector_score([100 + i * 2 for i in range(30)],
                         [100 + i for i in range(30)],
                         [100 + i for i in range(30)], .8,
                         {"strong": 75, "positive": 60, "neutral": 45, "weak": 30})
    assert value["sector_state"] in {"STRONG", "POSITIVE"}
    assert value["relative"][5] > 0


def test_entry_gate_blocks_missing_and_risk_off_context():
    missing = entry_gate("CONFIRMED_ENTRY", 85, True, True, True, True, True,
                         None, None, gate_config())
    assert missing["decision"] == "WAIT" and missing["position_multiplier"] == 0
    risk_off = entry_gate("CONFIRMED_ENTRY", 85, True, True, True, True, True,
        {"global_score": 20, "global_state": "RISK_OFF"},
        {"sector_score": 80, "sector_state": "STRONG"}, gate_config())
    assert risk_off["decision"] == "WAIT"


def test_entry_gate_sizes_valid_context_and_exit_uses_context_as_adjustment():
    allowed = entry_gate("CONFIRMED_ENTRY", 85, True, True, True, True, True,
        {"global_score": 75, "global_state": "RISK_ON"},
        {"sector_score": 65, "sector_state": "POSITIVE"}, gate_config())
    assert allowed["decision"] == "CONFIRMED_ENTRY"
    assert allowed["position_multiplier"] == .85
    adjustment = exit_context_adjustment({"global_score": 30}, {"sector_score": 25})
    assert adjustment["risk_addition"] > 0


def test_unified_universe_deduplicates_and_retains_sources(db):
    apple = UniverseInstrument(symbol="AAPL", market="US", status="ACTIVE", first_seen=NOW)
    source_etf = UniverseInstrument(symbol="QQQ", market="US", status="ACTIVE", first_seen=NOW)
    db.add_all([apple, source_etf]); db.flush()
    db.add_all([
        UniverseMembership(universe_id=apple.id, fund_symbol="QQQ", source_name="TEST",
                           first_seen=NOW, last_seen=NOW, is_active=True),
        UniverseMembership(universe_id=apple.id, fund_symbol="SPY", source_name="TEST",
                           first_seen=NOW, last_seen=NOW, is_active=True),
        UniverseMembership(universe_id=source_etf.id, fund_symbol="QQQ", source_name="TEST",
                           first_seen=NOW, last_seen=NOW, is_active=True),
    ]); db.commit()
    rows, metadata, stats = QmrRepository(db).unified_universe(
        NOW + timedelta(seconds=1), ["QQQ", "SPY", "SOXX"])
    assert [row.symbol for row in rows] == ["AAPL"]
    assert metadata["AAPL"] == {"source_universes": ["QQQ", "SPY"], "source_count": 2}
    assert stats["duplicates_removed"] == 1
    assert stats["source_statuses"]["SOXX"] == "DATA_UNAVAILABLE"


def test_context_snapshots_are_idempotent_and_historical(db):
    repository = MarketContextRepository(db)
    global_row = MarketContextSnapshot(timestamp=NOW, session="REGULAR", global_score=70,
        global_state="RISK_ON", asset_scores_json={}, source_timestamps_json={},
        data_quality_json={}, model_version="market-context-v1")
    first, created = repository.save_global(global_row); db.commit()
    duplicate, created_again = repository.save_global(MarketContextSnapshot(
        timestamp=NOW, session="REGULAR", global_score=70, global_state="RISK_ON",
        asset_scores_json={}, source_timestamps_json={}, data_quality_json={},
        model_version="market-context-v1"))
    assert created is True and created_again is False and duplicate.id == first.id
    assert repository.historical_global(end=NOW)[0].global_state == "RISK_ON"


def test_historical_comparison_is_explicit_when_samples_absent():
    report = compare_context_variants([
        {"return": 5, "global_state": "RISK_ON", "sector_state": "STRONG"},
        {"return": -3, "global_state": "RISK_OFF", "sector_state": "WEAK"},
    ])
    assert report["BASELINE"]["sample_count"] == 2
    assert report["GLOBAL_SECTOR_GATE"]["win_rate"] == 1
    assert compare_context_variants([])["BASELINE"]["win_rate"] is None
