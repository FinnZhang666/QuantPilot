"""Explicitly gated Moomoo simulated-account adapter."""
from typing import Any

from app.core.config import get_settings
from app.core.enums import OrderSide, OrderType, TradingMode
from app.data.providers.moomoo import MoomooConnectionManager
from app.execution.base import ExecutionBroker


class MoomooPaperBroker(ExecutionBroker):
    """Submit only LIMIT orders to an account reported as SIMULATE."""

    paper_only = True

    def __init__(self, settings=None, manager=None):
        self.settings = settings or get_settings()
        self.manager = manager or MoomooConnectionManager(
            self.settings.moomoo_opend_host, self.settings.moomoo_opend_port,
            self.settings.moomoo_connection_timeout_seconds,
        )

    def _guard(self):
        if not self.paper_only:
            raise RuntimeError("Moomoo adapter must remain paper-only")
        if self.settings.trading_mode != TradingMode.MOOMOO_PAPER:
            raise RuntimeError("TRADING_MODE must be MOOMOO_PAPER")
        if not self.settings.enable_moomoo_paper:
            raise RuntimeError("ENABLE_MOOMOO_PAPER must be true")
        if self.settings.moomoo_live_trading_enabled or self.settings.moomoo_allow_order_submission:
            raise RuntimeError("Real trading flags must remain disabled")

    def _paper_account(self, context, sdk):
        ret, frame = context.get_acc_list()
        if ret != sdk.RET_OK:
            raise RuntimeError("Moomoo paper account discovery failed")
        for row in frame.to_dict("records"):
            if "SIMULATE" in str(row.get("trd_env", "")).upper():
                return row.get("acc_id")
        raise RuntimeError("No Moomoo SIMULATE account found")

    async def submit_order(self, order: Any) -> Any:
        self._guard()
        if order.order_type != OrderType.LIMIT or order.limit_price is None:
            raise ValueError("Moomoo paper adapter accepts LIMIT orders only")
        sdk = self.manager._sdk()
        context = self.manager.open_us_trade_context()
        try:
            account = self._paper_account(context, sdk)
            side = sdk.TrdSide.BUY if order.side == OrderSide.BUY else sdk.TrdSide.SELL
            code = order.symbol.upper()
            if not code.startswith("US."):
                code = "US." + code
            ret, frame = context.place_order(
                price=float(order.limit_price), qty=float(order.quantity), code=code,
                trd_side=side, order_type=sdk.OrderType.NORMAL,
                trd_env=sdk.TrdEnv.SIMULATE, acc_id=account,
                remark="TradeCompanion-paper-smoke",
            )
            if ret != sdk.RET_OK:
                raise RuntimeError("Moomoo simulated order rejected")
            row = frame.to_dict("records")[0]
            return {"order_id": str(row.get("order_id", "")), "code": code,
                    "status": str(row.get("order_status", "SUBMITTED")),
                    "environment": "SIMULATE", "account": "MASKED"}
        finally:
            self.manager.close_all()

    async def cancel_order(self, order_id: Any) -> Any:
        self._guard()
        sdk = self.manager._sdk()
        context = self.manager.open_us_trade_context()
        try:
            account = self._paper_account(context, sdk)
            ret, frame = context.modify_order(
                sdk.ModifyOrderOp.CANCEL, str(order_id), 0, 0,
                trd_env=sdk.TrdEnv.SIMULATE, acc_id=account,
            )
            if ret != sdk.RET_OK:
                raise RuntimeError("Moomoo simulated order cancellation failed")
            return {"order_id": str(order_id), "status": "CANCEL_REQUESTED",
                    "environment": "SIMULATE", "account": "MASKED"}
        finally:
            self.manager.close_all()

    async def get_order(self, order_id: Any) -> Any:
        self._guard()
        sdk = self.manager._sdk()
        context = self.manager.open_us_trade_context()
        try:
            account = self._paper_account(context, sdk)
            ret, frame = context.order_list_query(
                order_id=str(order_id), trd_env=sdk.TrdEnv.SIMULATE,
                acc_id=account, refresh_cache=True,
            )
            if ret != sdk.RET_OK or frame.empty:
                raise KeyError(str(order_id))
            row = frame.to_dict("records")[0]
            return {"order_id": str(row.get("order_id", "")),
                    "status": str(row.get("order_status", "UNKNOWN")),
                    "filled_quantity": row.get("dealt_qty"),
                    "average_fill_price": row.get("dealt_avg_price"),
                    "reject_reason": row.get("remark") or row.get("last_err_msg"),
                    "code": str(row.get("code", "")), "environment": "SIMULATE",
                    "account": "MASKED"}
        finally:
            self.manager.close_all()
