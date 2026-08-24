from decimal import Decimal

from app.candidate_pool.universe import DatabaseUniverseProvider
from app.core.config import Settings
from app.universe.models import UniverseSource
from app.universe.parser import normalize_symbol, parse_csv
from app.universe.service import UniverseService


CSV_QQQ = b"metadata,row\nHolding Ticker,Holding Name,Weight (%)\nAAPL,Apple Inc,8.5\nMSFT,Microsoft,7.2\n"
CSV_SPY = b"Ticker,Name,Weight,Sector,Industry\nAAPL,Apple Inc,7.0,Technology,Hardware\nBRK/B,Berkshire,1.5,Financials,Insurance\n"


class FakeDownloader:
    def __init__(self, content):
        self.content = content

    def fetch(self, source, force=False):
        return self.content[source.fund_symbol], "TEST"


def settings(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("""version: '1.0'
sources:
  - {fund_symbol: QQQ, provider: TEST, enabled: true, format: csv, parser: generic, url: 'https://example/qqq'}
  - {fund_symbol: SPY, provider: TEST, enabled: true, format: csv, parser: generic, url: 'https://example/spy'}
""", encoding="utf-8")
    return Settings(universe_sources_file=str(path), universe_cache_directory=str(tmp_path / "cache"))


def test_parser_normalizes_and_deduplicates():
    assert normalize_symbol("US.aapl") == "AAPL"
    assert normalize_symbol("BRK/B") == "BRK.B"
    rows = parse_csv(CSV_QQQ + b"AAPL,Apple Duplicate,9.0\n")
    assert [row.symbol for row in rows] == ["AAPL", "MSFT"]
    assert rows[0].weight == Decimal("9.0")


def test_update_deduplicates_cross_fund_and_exposes_compatibility_fields(db, tmp_path):
    service = UniverseService(db, settings(tmp_path), FakeDownloader({"QQQ": CSV_QQQ, "SPY": CSV_SPY}))
    run = service.update()
    assert run.status == "SUCCESS"
    items, total = service.list(status="ACTIVE", limit=100, offset=0)
    assert total == 3
    apple = next(item for item in items if item["symbol"] == "AAPL")
    assert apple["qqq_member"] is True and apple["spy_member"] is True
    assert apple["qqq_weight"] == "8.50000000"


def test_removed_constituent_is_inactive_not_deleted(db, tmp_path):
    config = settings(tmp_path)
    downloader = FakeDownloader({"QQQ": CSV_QQQ, "SPY": CSV_SPY})
    service = UniverseService(db, config, downloader)
    service.update()
    downloader.content["QQQ"] = b"Ticker,Name,Weight\nMSFT,Microsoft,7.2\n"
    downloader.content["SPY"] = b"Ticker,Name,Weight\nBRK/B,Berkshire,1.5\n"
    run = service.update(force=True)
    assert run.inactivated_count == 2
    apple = service.get("AAPL")
    assert apple is not None and apple["status"] == "INACTIVE"


def test_strategy_provider_reads_only_active_database_universe(db, tmp_path):
    service = UniverseService(db, settings(tmp_path), FakeDownloader({"QQQ": CSV_QQQ, "SPY": CSV_SPY}))
    service.update()
    rows = DatabaseUniverseProvider(db).get_symbols()
    assert {row.symbol for row in rows} == {"AAPL", "MSFT", "BRK.B"}
    assert all(row.source.startswith("UNIVERSE:") for row in rows)
