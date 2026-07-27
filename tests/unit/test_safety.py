import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import LiveTradingDisabledError
from app.database.models import PaperOrder, Portfolio
from app.execution.live_blocked import LiveTradingBlockedBroker


@pytest.mark.asyncio
@pytest.mark.parametrize("method,arg", [
    ("submit_order", {}),
    ("cancel_order", 1),
    ("get_order", 1),
])
async def test_live_broker_always_refuses(method, arg):
    broker = LiveTradingBlockedBroker()
    with pytest.raises(LiveTradingDisabledError):
        await getattr(broker, method)(arg)


def test_execution_mode_rejects_live(db):
    p = Portfolio(code="P", name="P", initial_cash=1, cash=1, equity=1)
    db.add(p)
    db.commit()
    db.add(
        PaperOrder(
            portfolio_id=p.id,
            symbol="AAPL",
            side="BUY",
            order_type="MARKET",
            quantity=1,
            signal_price=1,
            status="PENDING",
            execution_mode="LIVE",
            market_session="REGULAR",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
