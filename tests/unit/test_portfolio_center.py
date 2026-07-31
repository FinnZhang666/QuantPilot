from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import inspect

from app.database.models import PortfolioHolding
from app.portfolio_center.errors import DuplicateDefaultPortfolio, DuplicatePortfolioName, DuplicateSymbol, PermissionDenied, ValidationError
from app.portfolio_center.formatter import format_holding_detail, format_holding_summary, format_portfolio_holdings, format_portfolio_statistics, format_portfolio_summary, format_portfolio_watchlist
from app.portfolio_center.service import HoldingService, PortfolioService, PortfolioStatisticsService, WatchlistService


def portfolio(db, user="user-a", name="My Portfolio", default=False):
    return PortfolioService(db).create_portfolio(user, name, currency="USD", is_default=default)


def test_portfolio_create_normalize_duplicate_and_first_default(db):
    row = portfolio(db, name="  My   Portfolio ")
    assert row.name == "My Portfolio" and row.normalized_name == "my portfolio" and row.is_default
    with pytest.raises(DuplicatePortfolioName): portfolio(db, name="my portfolio")


def test_multiple_users_may_share_name_and_ownership_is_enforced(db):
    row = portfolio(db)
    assert portfolio(db, user="user-b").id != row.id
    with pytest.raises(PermissionDenied): PortfolioService(db).get(row.id, "user-b")


def test_set_default_is_unique_and_default_must_be_active(db):
    first = portfolio(db, name="First"); second = portfolio(db, name="Second")
    PortfolioService(db).set_default(second.id); db.refresh(first)
    assert second.is_default and not first.is_default
    PortfolioService(db).update(first.id, status="INACTIVE")
    with pytest.raises(ValidationError): PortfolioService(db).set_default(first.id)


def test_default_cannot_be_deactivated_and_inactive_can_restore(db):
    row = portfolio(db)
    with pytest.raises(DuplicateDefaultPortfolio): PortfolioService(db).update(row.id, status="INACTIVE")
    second = portfolio(db, name="Second"); PortfolioService(db).set_default(second.id)
    PortfolioService(db).update(row.id, status="INACTIVE")
    assert PortfolioService(db).update(row.id, status="ACTIVE").status == "ACTIVE"


@pytest.mark.parametrize("currency", ["EUR", "", "BTC"])
def test_currency_validation(db, currency):
    with pytest.raises(ValidationError): PortfolioService(db).create_portfolio("u", "Name", currency=currency)


def test_empty_name_and_user_validation(db):
    with pytest.raises(ValidationError): PortfolioService(db).create_portfolio("", "Name")
    with pytest.raises(ValidationError): PortfolioService(db).create_portfolio("u", "  ")


def test_open_holding_decimal_precision_and_defaults(db):
    p = portfolio(db)
    row = HoldingService(db).open_holding(p.id, " soxl ", "us", "long", "1.12345678", "28.12345678")
    assert row.symbol == "SOXL" and row.status == "OPEN"
    assert row.quantity == Decimal("1.12345678") and row.average_cost == Decimal("28.12345678")


@pytest.mark.parametrize("quantity", ["0", "-1", "nan", "bad"])
def test_holding_rejects_invalid_quantity(db, quantity):
    p = portfolio(db)
    with pytest.raises(ValidationError): HoldingService(db).open_holding(p.id, "QQQ", "US", "LONG", quantity, "0")


def test_average_cost_zero_allowed_negative_rejected(db):
    p = portfolio(db)
    assert HoldingService(db).open_holding(p.id, "QQQ", "US", "LONG", "1", "0").average_cost == 0
    with pytest.raises(ValidationError): HoldingService(db).open_holding(p.id, "SPY", "US", "LONG", "1", "-1")


@pytest.mark.parametrize("symbol,market", [("", "US"), ("BAD SYMBOL", "US"), ("QQQ", "XX")])
def test_holding_symbol_market_validation(db, symbol, market):
    p = portfolio(db)
    with pytest.raises(ValidationError): HoldingService(db).open_holding(p.id, symbol, market, "LONG", 1, 1)


def test_close_holding_and_double_close(db):
    p = portfolio(db); opened = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = HoldingService(db).open_holding(p.id, "QQQ", "US", "LONG", 1, 1, opened_at=opened)
    closed = HoldingService(db).close_holding(row.id, opened + timedelta(hours=1), "Manual close")
    assert closed.status == "CLOSED" and closed.notes == "Manual close"
    with pytest.raises(ValidationError): HoldingService(db).close_holding(row.id)


def test_close_before_open_rejected(db):
    p = portfolio(db); opened = datetime(2026, 1, 2, tzinfo=timezone.utc)
    row = HoldingService(db).open_holding(p.id, "QQQ", "US", "LONG", 1, 1, opened_at=opened)
    with pytest.raises(ValidationError): HoldingService(db).close_holding(row.id, opened - timedelta(seconds=1))


def test_holding_filters_pagination_and_stable_sort(db):
    p = portfolio(db); service = HoldingService(db)
    for symbol in ("QQQ", "SOXL", "PLTR"): service.open_holding(p.id, symbol, "US", "LONG", 1, 1)
    assert len(service.list_all(portfolio_id=p.id, page=1, page_size=2)) == 2
    assert service.count(portfolio_id=p.id, symbol="qqq", status="open") == 1
    assert service.list_open(p.id, page=1, page_size=10)[0].status == "OPEN"


def test_watchlist_unique_scope_order_move_delete(db):
    p1, p2 = portfolio(db), portfolio(db, name="Other")
    service = WatchlistService(db); one = service.add_symbol(p1.id, " pltr ", notes="Growth"); two = service.add_symbol(p1.id, "QQQ")
    assert (one.display_order, two.display_order) == (10, 20)
    with pytest.raises(DuplicateSymbol): service.add_symbol(p1.id, "PLTR")
    assert service.add_symbol(p2.id, "PLTR").id
    service.move_order(two.id, 5, p1.id)
    assert [x.symbol for x in service.list_symbols(p1.id)] == ["QQQ", "PLTR"]
    service.remove_symbol(one.id, p1.id); assert not service.exists(p1.id, "PLTR")


def test_watchlist_delete_does_not_affect_holding(db):
    p = portfolio(db); holding = HoldingService(db).open_holding(p.id, "QQQ", "US", "LONG", 1, 1)
    item = WatchlistService(db).add_symbol(p.id, "QQQ"); WatchlistService(db).remove_symbol(item.id, p.id)
    assert db.get(PortfolioHolding, holding.id) is not None


def test_statistics_empty_and_populated(db):
    p = portfolio(db); stats = PortfolioStatisticsService(db)
    assert stats.calculate(p.id)["total_holdings"] == 0
    service = HoldingService(db); a = service.open_holding(p.id, "QQQ", "US", "LONG", 1, 1)
    service.open_holding(p.id, "SOXS", "US", "SHORT", 1, 1); service.close_holding(a.id)
    WatchlistService(db).add_symbol(p.id, "PLTR"); result = stats.calculate(p.id)
    assert (result["total_holdings"], result["open_holdings"], result["closed_holdings"]) == (2, 1, 1)
    assert result["long_count"] == result["short_count"] == result["watchlist_count"] == 1
    assert result["earliest_holding_opened_at"] and result["latest_holding_opened_at"]


def test_foreign_key_delete_policies_declared(db):
    fks = inspect(db.bind).get_foreign_keys("portfolio_holdings")
    options = {fk["referred_table"]: fk["options"].get("ondelete") for fk in fks}
    assert options["trade_plans"] == "SET NULL" and options["user_positions"] == "SET NULL"


def test_formatters_are_safe_empty_decimal_and_bounded(db):
    p = portfolio(db); stats = PortfolioStatisticsService(db).calculate(p.id)
    assert "不是券商实时仓位" in format_portfolio_summary(p, stats)
    assert "暂无持仓" in format_portfolio_holdings([]) and "暂无关注" in format_portfolio_watchlist([])
    assert "当前持仓" in format_portfolio_statistics(stats)
    h = HoldingService(db).open_holding(p.id, "QQQ", "US", "LONG", "1.25", "28.5", notes="_*unsafe")
    assert "1.25" in format_holding_summary(h, p.name)
    detail = format_holding_detail(h, "中英文 Portfolio")
    assert "\\_\\*unsafe" in detail and len(detail) <= 4000
