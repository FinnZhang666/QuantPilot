import inspect
from pathlib import Path

from app.market_snapshot.models import MarketSnapshot
from app.market_snapshot.service import MarketSnapshotService
from app.symbol_overview.models import SymbolOverview
from app.symbol_overview.repository import SymbolOverviewRepository
from app.symbol_overview.service import SymbolOverviewService
from app.telegram_product.base import escape_markdown, limit_message
from app.telegram_product.presenter import TelegramPresenter
from tests.unit.test_market_snapshot import add_market


def test_dtos_are_not_orm_models():
    assert not hasattr(MarketSnapshot, "__table__")
    assert not hasattr(SymbolOverview, "__table__")


def test_overview_reuses_snapshot_loaded_sources():
    source = inspect.getsource(SymbolOverviewService.get)
    assert "get_snapshot_context" in source
    assert not hasattr(SymbolOverviewRepository, "latest_plan")
    assert not hasattr(SymbolOverviewRepository, "latest_holding")


def test_snapshot_request_cache_reuses_dto_and_sources(db):
    add_market(db)
    service = MarketSnapshotService(db)
    first, first_sources = service.get_snapshot_context("SOXL")
    second, second_sources = service.get_snapshot_context("SOXL")
    assert first is second and first_sources is second_sources


def test_formatter_base_is_single_escape_and_limit_source():
    assert escape_markdown("A_B") == "A\\_B"
    assert len(limit_message("x" * 5000)) == 4000
    for module in ("app/market_snapshot/formatter.py", "app/portfolio_center/formatter.py",
                   "app/telegram_product/presenter.py"):
        text = Path(module).read_text(encoding="utf-8")
        assert "app.telegram_product.base" in text


def test_recent_product_layers_have_no_print_network_or_order_calls():
    roots = (Path("app/market_snapshot"), Path("app/symbol_overview"), Path("app/telegram_product"))
    text = "\n".join(path.read_text(encoding="utf-8") for root in roots for path in root.glob("*.py"))
    assert "print(" not in text
    for forbidden in ("send_text(", "requests.", "httpx.", "place_order", "submit_order"):
        assert forbidden not in text


def test_dashboard_uses_shared_navigation_empty_and_request_cache():
    text = Path("app/dashboard/static/dashboard.js").read_text(encoding="utf-8")
    assert "relatedObjects" in text and "symbolHeader" in text
    assert "const empty=" in text and "apiCache" in text


def test_telegram_presenter_does_not_access_repository():
    source = inspect.getsource(TelegramPresenter)
    assert "Repository" not in source and ".db" not in source
