from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import yaml

from app.recovery.scoring import capital_flow, combine, stabilization, stage_and_entry, technical
from app.database.models import Instrument, MarketBar, MispricingScoreRecord, QmrCandidateRecord, QualityScoreRecord, UniverseInstrument
from app.recovery.repository import RecoveryRepository


CONFIG = yaml.safe_load(open("config/recovery_v1.yaml", encoding="utf-8"))
NOW = datetime(2026, 8, 24, 15, 0, tzinfo=timezone.utc)


def bar(index, close, volume=100, interval_minutes=5, trading_date="2026-08-24", session="REGULAR"):
    value = Decimal(str(close))
    opened = value - Decimal("0.2")
    return SimpleNamespace(
        timestamp_utc=NOW + timedelta(minutes=index * interval_minutes),
        timestamp_market=NOW + timedelta(minutes=index * interval_minutes),
        trading_date=trading_date, market_session=session,
        open=opened, high=value + Decimal("0.4"), low=value - Decimal("0.4"),
        close=value, volume=volume,
    )


def rows(values, volumes=None, interval=5, date="2026-08-24"):
    volumes = volumes or [100] * len(values)
    return [bar(i, value, volumes[i], interval, date) for i, value in enumerate(values)]


def test_case_a_continuing_lower_lows_waits_even_if_oversold():
    previous = None
    stage, entry, _ = stage_and_entry(25, 15, previous, 70, CONFIG)
    assert stage == "PANIC"
    assert entry == "WAIT"


def test_case_b_stopped_falling_without_flow_is_observe():
    values = [100 - i for i in range(12)] + [89, 89.2, 89.1, 89.4, 89.5, 89.7, 89.8, 90]
    score, components, _, _ = stabilization({"5m": rows(values)}, CONFIG)
    stage, entry, _ = stage_and_entry(52, score, None, 88.6, CONFIG)
    assert components["no_new_low"]["available"] is True
    assert entry == "OBSERVE"


def test_case_c_stabilization_volume_and_vwap_recovery_reaches_early_entry():
    score, coverage = combine({"stabilization": 80, "capital_flow": 82, "technical": 65, "sector": 55, "market": 55}, CONFIG)
    stage, entry, _ = stage_and_entry(score, 80, None, 90, CONFIG)
    assert coverage == 1
    assert score >= 65
    assert entry in ("EARLY_ENTRY", "CONFIRMED_ENTRY", "STRONG_ENTRY")


def test_case_d_sector_confirmation_reaches_confirmed_entry():
    score, _ = combine({"stabilization": 82, "capital_flow": 85, "technical": 78, "sector": 90, "market": 75}, CONFIG)
    stage, entry, _ = stage_and_entry(score, 82, None, 90, CONFIG)
    assert stage in ("RECOVERY_CONFIRMED", "TREND_RECOVERY")
    assert entry in ("CONFIRMED_ENTRY", "STRONG_ENTRY")


def test_case_e_breaking_signal_low_marks_failed_recovery():
    previous = SimpleNamespace(entry_status="CONFIRMED_ENTRY", session_low=Decimal("100"))
    stage, entry, reason = stage_and_entry(80, 80, previous, 99, CONFIG)
    assert (stage, entry) == ("FAILED_RECOVERY", "FAILED")
    assert "跌破" in reason


def test_case_f_missing_active_buy_data_is_partial_and_renormalized():
    historical = []
    for day in range(20):
        date = "2026-07-%02d" % (day + 1)
        historical.extend(rows([100, 100.2, 100.4], [100, 100, 100], date=date))
    current = rows([99, 99.2, 99.5, 100, 100.4, 101], [120, 130, 160, 200, 220, 250])
    score, components, _, status = capital_flow(historical + current, CONFIG, active_buy_factor=None)
    assert status == "PARTIAL"
    assert components["active_buy"]["available"] is False
    assert score > 0


def test_technical_confirmation_uses_macd_dif_dea_histogram_and_rsi():
    values = [100 - i * .4 for i in range(20)] + [92 + i * .6 for i in range(20)]
    score, components, _ = technical(rows(values, interval=30), CONFIG)
    assert score is not None
    assert set(components["macd"]) >= {"dif", "dea", "histogram"}
    assert components["rsi"]["value"] is not None


def test_session_specific_rvol_does_not_mix_premarket():
    regular = rows([100] * 10, [100] * 10)
    premarket = [bar(i, 100, 100000, session="PRE_MARKET") for i in range(10)]
    score_regular, _, _, _ = capital_flow(regular, CONFIG)
    score_mixed, _, _, _ = capital_flow(premarket + regular, CONFIG)
    assert score_regular == score_mixed


def qmr_candidate(db, symbol="TEST", status="WATCH"):
    universe = UniverseInstrument(symbol=symbol, market="US", status="ACTIVE")
    db.add(universe); db.flush()
    quality = QualityScoreRecord(universe_id=universe.id, symbol=symbol, evaluation_time=NOW,
        quality_score=80, score_components_json={}, data_sources_json=[], data_confidence="HIGH",
        data_coverage=1, model_version="qmr-v1")
    mispricing = MispricingScoreRecord(universe_id=universe.id, symbol=symbol, evaluation_time=NOW,
        mispricing_score=85, fundamental_risk="LOW", event_risk="A", news_confidence="HIGH",
        score_components_json={}, data_sources_json=[], data_confidence="HIGH", model_version="qmr-v1")
    db.add_all([quality, mispricing]); db.flush()
    candidate = QmrCandidateRecord(universe_id=universe.id, quality_score_id=quality.id,
        mispricing_score_id=mispricing.id, symbol=symbol, evaluation_time=NOW,
        quality_score=80, mispricing_score=85, combined_score=83, fundamental_risk="LOW",
        event_risk="A", candidate_status=status, score_components_json={}, data_sources_json=[],
        data_confidence="HIGH", model_version="qmr-v1")
    db.add(candidate); db.commit()
    return candidate


def test_repository_reads_only_latest_watch_candidates(db):
    watched = qmr_candidate(db, "WATCHED", "WATCH")
    qmr_candidate(db, "REJECTED", "REJECT")
    rows_found = RecoveryRepository(db).watch_candidates(NOW + timedelta(minutes=1), model_version="qmr-v1")
    assert [row.id for row in rows_found] == [watched.id]


def test_recovery_save_is_idempotent_and_records_state_change(db):
    candidate = qmr_candidate(db)
    values = {
        "qmr_candidate_id": candidate.id, "symbol": "TEST", "evaluation_time": NOW,
        "price": 101, "session_low": 95, "session_high": 102, "low_recovery_pct": .063,
        "stabilization_score": 80, "capital_flow_score": 75, "technical_score": None,
        "sector_recovery_score": None, "market_recovery_score": None,
        "global_context_score": None, "recovery_score": 78,
        "recovery_stage": "RECOVERY_CONFIRMED", "entry_status": "CONFIRMED_ENTRY",
        "market_state": "UNKNOWN", "trading_session": "REGULAR",
        "capital_flow_data": "PARTIAL", "score_components_json": {},
        "data_sources_json": ["TEST"], "data_confidence": "LOW",
        "model_version": "recovery-v1", "failure_reason": None,
    }
    repository = RecoveryRepository(db)
    first, created, event = repository.save(values, ["test"])
    second, created_again, event_again = repository.save(values, ["test"])
    assert first.id == second.id
    assert (created, event) == (True, True)
    assert (created_again, event_again) == (False, False)
    assert len(repository.events("TEST")) == 1


def test_recovery_repository_excludes_future_bars(db):
    instrument = Instrument(symbol="US.PIT", market="US", code="PIT")
    db.add(instrument); db.flush()
    for timestamp, close in ((NOW - timedelta(minutes=5), 10), (NOW + timedelta(minutes=5), 100)):
        db.add(MarketBar(instrument_id=instrument.id, symbol="US.PIT", interval="5m",
            timestamp_utc=timestamp, timestamp_market=timestamp, trading_date="2026-08-24",
            open=close, high=close + 1, low=close - 1, close=close, volume=100,
            is_blank=False, market_session="REGULAR", adjustment_type="FORWARD"))
    db.commit()
    found = RecoveryRepository(db).bars("PIT", "5m", NOW)
    assert len(found) == 1
    assert found[0].close == Decimal("10.00000000")
