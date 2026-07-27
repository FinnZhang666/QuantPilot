import pytest
from sqlalchemy import select

from app.core.enums import OrderSide, OrderStatus, OrderType
from app.database.models import PaperPosition, Portfolio
from app.execution.internal_paper import InternalPaperBroker
from app.execution.models import OrderRequest


def portfolio(db):
    row = Portfolio(
        code="TEST", name="Test", initial_cash=100000, cash=100000, equity=100000
    )
    db.add(row)
    db.commit()
    return row


def request(portfolio_id, side=OrderSide.BUY, order_type=OrderType.MARKET, **kwargs):
    return OrderRequest(
        portfolio_id=portfolio_id,
        symbol="AAPL",
        side=side,
        order_type=order_type,
        quantity=kwargs.pop("quantity", 10),
        reference_price=kwargs.pop("reference_price", 100),
        **kwargs,
    )


def test_market_matching(db):
    p = portfolio(db)
    result = InternalPaperBroker(db, slippage_bps=8).match(request(p.id))
    assert result.status == OrderStatus.FILLED
    assert result.filled_price == 100.08


def test_limit_buy_matching(db):
    p = portfolio(db)
    result = InternalPaperBroker(db).match(
        request(p.id, order_type=OrderType.LIMIT, limit_price=99, market_low=98)
    )
    assert result.status == OrderStatus.FILLED
    assert result.filled_price == 99


def test_limit_sell_matching(db):
    p = portfolio(db)
    result = InternalPaperBroker(db).match(
        request(
            p.id,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            limit_price=101,
            market_high=102,
        )
    )
    assert result.status == OrderStatus.FILLED
    assert result.filled_price == 101


def test_limit_not_reached(db):
    p = portfolio(db)
    result = InternalPaperBroker(db).match(
        request(p.id, order_type=OrderType.LIMIT, limit_price=99, market_low=99.5)
    )
    assert result.status == OrderStatus.PENDING


@pytest.mark.asyncio
async def test_portfolio_cash_update(db):
    p = portfolio(db)
    broker = InternalPaperBroker(db, slippage_bps=0)
    await broker.submit_order(request(p.id, quantity=10, reference_price=100))
    db.refresh(p)
    assert p.cash == 99000


@pytest.mark.asyncio
async def test_position_average_cost_update(db):
    p = portfolio(db)
    broker = InternalPaperBroker(db, slippage_bps=0)
    await broker.submit_order(request(p.id, quantity=10, reference_price=100))
    await broker.submit_order(request(p.id, quantity=10, reference_price=120))
    position = db.scalar(select(PaperPosition).where(PaperPosition.portfolio_id == p.id))
    assert position.quantity == 20
    assert position.average_cost == 110
