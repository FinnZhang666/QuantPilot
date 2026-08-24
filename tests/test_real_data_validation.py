from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from decimal import Decimal
from pathlib import Path

import yaml

from app.data.capabilities import money_flow_capability
from app.data.quality import DataStatus, assess_quality
from app.qmr.providers import DatabaseFundamentalsProvider, FundamentalsProvider
from app.qmr.scoring import _valuation_peer_assessment, mispricing_score, quality_score
from app.qmr_exit.scoring import evaluate_money_flow
from app.universe.service import UniverseService
from app.database.models import FundamentalSnapshot


CONFIG = yaml.safe_load(Path("config/qmr_v1.yaml").read_text(encoding="utf-8"))


def fundamental(good=True):
    sign = 1 if good else -1
    now = datetime.now(timezone.utc)
    return FundamentalSnapshot(symbol="TEST", period_end=now, available_at=now, source="TEST",
        net_income_ttm=100 * sign, eps_ttm=5 * sign, operating_margin=Decimal(".25") * sign,
        roe=Decimal(".20") * sign, roic=Decimal(".16") * sign,
        revenue_yoy=Decimal(".20") * sign, eps_yoy=Decimal(".20") * sign,
        operating_cash_flow=100 * sign, free_cash_flow=80 * sign, cash=200, debt=50,
        debt_to_equity=Decimal(".3"), interest_coverage=10)


def bars(values):
    return [SimpleNamespace(close=Decimal(str(value))) for value in values]


CSV = b"Ticker,Name,Weight\nAAPL,Apple,8.0\nMSFT,Microsoft,7.0\n"


class ResilientDownloader:
    def __init__(self, outcomes, cached=None):
        self.outcomes, self.cached, self.saved = outcomes, cached or {}, []

    def fetch_remote(self, source):
        value = self.outcomes[source.provider]
        if isinstance(value, Exception): raise value
        return value, datetime.now(timezone.utc)

    def save_last_known_good(self, source, content, fetched_at=None):
        self.saved.append(source.provider)

    def load_last_known_good(self, source):
        return self.cached.get(source.provider)


def _universe_settings(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("""version: '2.0'
sources:
  - {fund_symbol: QQQ, provider: PRIMARY, role: PRIMARY, priority: 10, enabled: true, format: csv, parser: generic, url: 'https://primary'}
  - {fund_symbol: QQQ, provider: FALLBACK, role: FALLBACK, priority: 20, enabled: true, format: csv, parser: generic, url: 'https://fallback'}
""", encoding="utf-8")
    from app.core.config import Settings
    return Settings(universe_sources_file=str(path), universe_cache_directory=str(tmp_path / "cache"))


def test_universe_primary_and_fallback_and_lkg_are_distinct(db, tmp_path):
    settings = _universe_settings(tmp_path)
    primary = UniverseService(db, settings, ResilientDownloader({"PRIMARY": CSV, "FALLBACK": RuntimeError()}))
    run = primary.update()
    assert run.summary_json["sources"][0]["actual_source"] == "PRIMARY"
    fallback = UniverseService(db, settings, ResilientDownloader({"PRIMARY": RuntimeError(), "FALLBACK": CSV}))
    run = fallback.update()
    assert run.summary_json["sources"][0]["fallback_used"] is True
    before = fallback.list(status="ACTIVE", limit=100, offset=0)[1]
    metadata = {"downloaded_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
    lkg = UniverseService(db, settings, ResilientDownloader(
        {"PRIMARY": RuntimeError(), "FALLBACK": RuntimeError()}, {"PRIMARY": (CSV, metadata)}))
    run = lkg.update()
    assert run.status == "PARTIAL_SUCCESS"
    assert run.summary_json["sources"][0]["cache_used"] is True
    assert lkg.list(status="ACTIVE", limit=100, offset=0)[1] == before


def test_quality_missing_factors_are_reweighted_not_zeroed():
    full = fundamental(True)
    partial = fundamental(True)
    partial.roe = partial.roic = partial.operating_margin = None
    context = {"industry_relative_strength": None, "qqq_weight": None,
               "spy_weight": None, "average_dollar_volume": None}
    score, _, coverage = quality_score(partial, context, CONFIG)
    full_score, _, full_coverage = quality_score(full, context, CONFIG)
    assert score > 0
    assert coverage < full_coverage
    assert abs(score - full_score) < 20


def test_fundamentals_provider_contract_and_point_in_time(db):
    assert issubclass(DatabaseFundamentalsProvider, FundamentalsProvider)
    at = datetime.now(timezone.utc)
    old, future = fundamental(True), fundamental(False)
    old.symbol = future.symbol = "PIT2"
    old.available_at, future.available_at = at - timedelta(days=1), at + timedelta(days=1)
    db.add_all([old, future]); db.commit()
    assert DatabaseFundamentalsProvider(db).get_as_of("PIT2", at).id == old.id


def test_peer_hierarchy_and_low_sample_confidence():
    result = _valuation_peer_assessment({
        "current": {"trailing_pe": 10},
        "industry_peers": [{"trailing_pe": 20}, {"trailing_pe": 25}],
        "sector_peers": [{"trailing_pe": 30}] * 10,
    })
    assert result["peer_method"] == "INDUSTRY"
    assert result["peer_count"] == 2 and result["peer_confidence"] == "LOW"


def test_mispricing_missing_inputs_report_coverage():
    event = SimpleNamespace(event_risk="UNKNOWN", confidence="LOW")
    score, details = mispricing_score(bars([100, 90]), [], [], event, CONFIG)
    assert score >= 0
    assert details["coverage"] < 1
    assert details["missing_factors"]


def test_money_flow_statuses_and_unknown_regime():
    missing = evaluate_money_flow(None)
    assert missing["data_status"] == "UNAVAILABLE" and missing["regime"] == "UNKNOWN"
    partial = {"super_large_net": 1, "large_net": 1, "medium_net": 1,
               "small_net": -1, "total_turnover": 100}
    result = evaluate_money_flow(partial)
    assert result["data_status"] in {"AVAILABLE", "PARTIAL"}
    assert result["coverage"] < 1 and result["regime"] == "UNKNOWN"
    capability = money_flow_capability("AAPL")
    assert capability.supported and "REGULAR" in capability.session_supported
    unsupported = money_flow_capability("TEST", market="XX")
    assert not unsupported.supported


def test_data_quality_uses_per_type_freshness():
    timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
    assert assess_quality("intraday_bars", timestamp, 1, "TEST").status == DataStatus.STALE.value
    assert assess_quality("fundamentals", timestamp, 1, "TEST").status == DataStatus.AVAILABLE.value
