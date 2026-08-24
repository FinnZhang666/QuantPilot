from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import yaml
from fastapi.encoders import jsonable_encoder

from app.database.models import FundamentalSnapshot, UniverseInstrument
from app.qmr.providers import EventAssessment, NoNewsProvider
from app.qmr.repository import QmrRepository
from app.qmr.scoring import mispricing_score, quality_score


CONFIG = yaml.safe_load(open("config/qmr_v1.yaml", encoding="utf-8"))


def fundamental(good=True):
    sign = 1 if good else -1
    return FundamentalSnapshot(
        symbol="TEST", period_end=datetime.now(timezone.utc), available_at=datetime.now(timezone.utc), source="TEST",
        net_income_ttm=100 * sign, eps_ttm=5 * sign, operating_margin=Decimal("0.25") * sign,
        roe=Decimal("0.20") * sign, roic=Decimal("0.16") * sign,
        revenue_yoy=Decimal("0.20") * sign, eps_yoy=Decimal("0.20") * sign,
        quarterly_trend=Decimal("0.20") * sign, forward_earnings_growth=Decimal("0.20") * sign,
        operating_cash_flow=100 * sign, free_cash_flow=80 * sign, cash=200, debt=50 if good else 500,
        debt_to_equity=Decimal("0.3") if good else Decimal("4"), interest_coverage=10 if good else -1,
        sector_profit_trend=Decimal("0.2") * sign,
    )


def bars(values):
    return [SimpleNamespace(close=Decimal(str(value))) for value in values]


def test_case_a_quality_extreme_selloff_can_watch(db):
    q, qc, coverage = quality_score(fundamental(True), {
        "industry_relative_strength": 1, "qqq_weight": 8, "spy_weight": 2,
        "average_dollar_volume": 100_000_000,
    }, CONFIG)
    prices = bars([100 + i * .2 for i in range(100)] + [100, 98, 94, 90, 84, 78])
    benchmark = bars([100 + i * .1 for i in range(106)])
    event = EventAssessment("A", "LOW", "HIGH", "TEST_NEWS")
    m, mc = mispricing_score(prices, benchmark, benchmark, event, CONFIG)
    universe = UniverseInstrument(symbol="TEST", market="US", status="ACTIVE")
    db.add(universe); db.commit()
    row, _ = QmrRepository(db).save(universe, datetime.now(timezone.utc), q, qc, coverage, m, mc,
                                    event, ["TEST"], "HIGH", "qmr-v1", CONFIG["thresholds"])
    assert q >= 60 and m >= 65 and row.candidate_status == "WATCH"


def test_case_b_bad_company_is_rejected_despite_selloff(db):
    q, qc, coverage = quality_score(fundamental(False), {
        "industry_relative_strength": 0, "qqq_weight": 5, "spy_weight": 0,
        "average_dollar_volume": 100_000_000,
    }, CONFIG)
    universe = UniverseInstrument(symbol="BAD", market="US", status="ACTIVE")
    db.add(universe); db.commit()
    event = EventAssessment("A", "MEDIUM", "HIGH", "TEST")
    row, _ = QmrRepository(db).save(universe, datetime.now(timezone.utc), q, qc, coverage, 95, {}, event,
                                    ["TEST"], "HIGH", "qmr-v1", CONFIG["thresholds"])
    assert row.candidate_status == "REJECT"


def test_case_c_normal_volatility_is_no_signal(db):
    q, qc, coverage = quality_score(fundamental(True), {
        "industry_relative_strength": 1, "qqq_weight": 8, "spy_weight": 0,
        "average_dollar_volume": 100_000_000,
    }, CONFIG)
    universe = UniverseInstrument(symbol="CALM", market="US", status="ACTIVE")
    db.add(universe); db.commit()
    event = EventAssessment("A", "LOW", "HIGH", "TEST")
    row, _ = QmrRepository(db).save(universe, datetime.now(timezone.utc), q, qc, coverage, 30, {}, event,
                                    ["TEST"], "HIGH", "qmr-v1", CONFIG["thresholds"])
    assert row.candidate_status == "NO_SIGNAL"


def test_case_d_major_fundamental_risk_is_rejected(db):
    universe = UniverseInstrument(symbol="RISK", market="US", status="ACTIVE")
    db.add(universe); db.commit()
    event = EventAssessment("C", "HIGH", "HIGH", "TEST")
    row, _ = QmrRepository(db).save(universe, datetime.now(timezone.utc), 90, {}, 1, 95, {}, event,
                                    ["TEST"], "HIGH", "qmr-v1", CONFIG["thresholds"])
    assert row.candidate_status == "REJECT"


def test_case_e_missing_news_is_unknown_not_low_risk():
    event = NoNewsProvider().assess("MU", datetime.now(timezone.utc))
    assert event.event_risk == "UNKNOWN"
    assert event.fundamental_risk == "UNKNOWN"
    assert event.confidence == "LOW"


def test_point_in_time_fundamental_provider_never_reads_future(db):
    from app.qmr.providers import DatabaseFundamentalsProvider
    at = datetime.now(timezone.utc)
    old = fundamental(True); old.symbol = "PIT"; old.available_at = at - timedelta(days=2)
    future = fundamental(False); future.symbol = "PIT"; future.available_at = at + timedelta(days=2)
    db.add_all([old, future]); db.commit()
    assert DatabaseFundamentalsProvider(db).latest("PIT", at).id == old.id


def test_qmr_repository_never_reads_future_bar(db):
    from app.database.models import Instrument, MarketBar
    at = datetime.now(timezone.utc)
    instrument = Instrument(symbol="PIT", market="US", code="PIT")
    db.add(instrument)
    db.flush()
    db.add_all([
        MarketBar(instrument_id=instrument.id, symbol="PIT", interval="1d", timestamp_utc=at - timedelta(days=1),
                  timestamp_market=at - timedelta(days=1), trading_date="2026-08-23",
                  open=10, high=11, low=9, close=10, volume=100, is_blank=False,
                  market_session="REGULAR", adjustment_type="FORWARD"),
        MarketBar(instrument_id=instrument.id, symbol="PIT", interval="1d", timestamp_utc=at + timedelta(days=1),
                  timestamp_market=at + timedelta(days=1), trading_date="2026-08-25",
                  open=90, high=110, low=80, close=100, volume=999, is_blank=False,
                  market_session="REGULAR", adjustment_type="FORWARD"),
    ])
    db.commit()
    rows = QmrRepository(db).bars("PIT", at)
    assert len(rows) == 1
    assert rows[0].close == Decimal("10.000000")


def test_dry_run_evaluation_is_json_safe():
    payload = {
        "quality": 70, "mispricing": 80, "coverage": 0.8,
        "quality_components": {}, "mispricing_components": {},
        "event": EventAssessment("UNKNOWN", "UNKNOWN", "LOW", "NEWS:UNAVAILABLE"),
        "sources": ["UNIVERSE"], "confidence": "LOW",
    }
    from app.qmr.service import QmrService
    encoded = jsonable_encoder(QmrService._serialize_evaluation("TEST", payload))
    assert encoded["event_risk"] == "UNKNOWN"
    assert encoded["news_confidence"] == "LOW"
