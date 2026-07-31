import pytest

from app.portfolio_center.service import HoldingService
from app.symbol_overview.formatter import format_related_objects, format_symbol_overview
from app.symbol_overview.service import SymbolOverviewService
from tests.unit.test_market_snapshot import add_market, add_plan, add_portfolio


def test_symbol_overview_empty_related_objects(db):
    add_market(db, "QQQ")
    value = SymbolOverviewService(db).get("qqq")
    assert value.symbol == "QQQ"
    assert value.trade_plan is None and value.review is None and value.ai_analysis is None
    assert value.related_objects["snapshot"]["available"] is True
    assert value.related_objects["trade_plan"]["available"] is False


def test_symbol_overview_plan_and_manual_holding(db):
    add_market(db); plan = add_plan(db); portfolio = add_portfolio(db)
    holding = HoldingService(db).open_holding(
        portfolio.id, "SOXL", "US", "LONG", "3", "28.50", trade_plan_id=plan.id,
    )
    value = SymbolOverviewService(db).get("SOXL")
    assert value.trade_plan["plan_id"] == plan.plan_id
    assert value.holding["id"] == holding.id
    assert value.related_objects["holding"]["available"] is True
    assert value.related_objects["ai"]["can_generate"] is True


def test_symbol_overview_is_read_only(db):
    add_market(db)
    before = len(db.new), len(db.dirty), len(db.deleted)
    SymbolOverviewService(db).get("SOXL")
    assert before == (len(db.new), len(db.dirty), len(db.deleted))


def test_symbol_overview_serialization_reuses_snapshot_contract(db):
    add_market(db, price="32.15")
    result = SymbolOverviewService.serialize(SymbolOverviewService(db).get("SOXL"))
    assert result["snapshot"]["latest_price"] == "32.15000000"
    assert "related_objects" in result and "ai_history" in result


def test_symbol_overview_formatters(db):
    add_market(db, "QQQ")
    value = SymbolOverviewService(db).get("QQQ")
    assert "QQQ" in format_symbol_overview(value)
    assert "AI\nNONE" in format_related_objects(value)


def test_ai_entry_requires_existing_supported_object(db):
    add_market(db)
    with pytest.raises(ValueError, match="暂无可用于AI解释"):
        SymbolOverviewService(db).ai_entry("SOXL")


def test_ai_entry_dry_run_delegates_existing_companion_service(db):
    add_market(db); add_plan(db)
    result = SymbolOverviewService(db).ai_entry("SOXL", dry_run=True)
    assert result["generated_from"] == "TRADE_PLAN" and result["dry_run"] is True
