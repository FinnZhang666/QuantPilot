import asyncio
from types import SimpleNamespace

import pandas as pd
import pytest

from app.core.enums import OrderSide, OrderType, TradingMode
from app.execution.models import OrderRequest
from app.execution.moomoo_paper import MoomooPaperBroker


class Context:
    def get_acc_list(self): return 0, pd.DataFrame([{"acc_id": 7, "trd_env": "SIMULATE"}])
    def place_order(self, **kwargs):
        assert kwargs["trd_env"] == "SIMULATE" and kwargs["acc_id"] == 7
        return 0, pd.DataFrame([{"order_id": "paper-1", "order_status": "SUBMITTED"}])
    def modify_order(self, *args, **kwargs):
        assert kwargs["trd_env"] == "SIMULATE" and kwargs["acc_id"] == 7
        return 0, pd.DataFrame([{}])
    def order_list_query(self, **kwargs):
        assert kwargs["trd_env"] == "SIMULATE" and kwargs["acc_id"] == 7
        return 0, pd.DataFrame([{"order_id": "paper-1", "order_status": "CANCELLED", "code": "US.QQQ"}])


class Manager:
    def __init__(self):
        self.context = Context(); self.closed = 0
    def _sdk(self):
        return SimpleNamespace(RET_OK=0, TrdSide=SimpleNamespace(BUY="BUY", SELL="SELL"), OrderType=SimpleNamespace(NORMAL="NORMAL"), TrdEnv=SimpleNamespace(SIMULATE="SIMULATE"), ModifyOrderOp=SimpleNamespace(CANCEL="CANCEL"))
    def open_us_trade_context(self): return self.context
    def close_all(self): self.closed += 1


def settings(**overrides):
    values = {"trading_mode": TradingMode.MOOMOO_PAPER, "enable_moomoo_paper": True,
              "moomoo_live_trading_enabled": False, "moomoo_allow_order_submission": False,
              "moomoo_opend_host": "127.0.0.1", "moomoo_opend_port": 11111,
              "moomoo_connection_timeout_seconds": 1}
    values.update(overrides); return SimpleNamespace(**values)


def request(order_type=OrderType.LIMIT):
    return OrderRequest(portfolio_id=1, symbol="QQQ", side=OrderSide.BUY,
                        order_type=order_type, quantity=1, reference_price=700,
                        limit_price=1 if order_type == OrderType.LIMIT else None)


def test_submit_query_cancel_are_simulate_only():
    broker = MoomooPaperBroker(settings(), Manager())
    submitted = asyncio.run(broker.submit_order(request()))
    assert submitted["environment"] == "SIMULATE" and submitted["account"] == "MASKED"
    assert asyncio.run(broker.get_order("paper-1"))["status"] == "CANCELLED"
    assert asyncio.run(broker.cancel_order("paper-1"))["status"] == "CANCEL_REQUESTED"


def test_real_flags_and_market_orders_are_rejected():
    with pytest.raises(RuntimeError):
        asyncio.run(MoomooPaperBroker(settings(moomoo_live_trading_enabled=True), Manager()).submit_order(request()))
    with pytest.raises(ValueError):
        asyncio.run(MoomooPaperBroker(settings(), Manager()).submit_order(request(OrderType.MARKET)))
