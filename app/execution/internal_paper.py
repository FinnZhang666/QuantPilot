from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import OrderSide, OrderStatus, OrderType, TradingMode
from app.database.models import PaperOrder, PaperPosition, Portfolio, Trade
from app.execution.base import ExecutionBroker
from app.execution.models import ExecutionResult, OrderRequest


class InternalPaperBroker(ExecutionBroker):
    def __init__(self, db: Session, slippage_bps: int = 8):
        self.db = db
        self.slippage_bps = slippage_bps

    def match(self, order: OrderRequest) -> ExecutionResult:
        if order.order_type == OrderType.MARKET:
            direction = 1 if order.side == OrderSide.BUY else -1
            price = order.reference_price * (1 + direction * self.slippage_bps / 10_000)
            return ExecutionResult(status=OrderStatus.FILLED, filled_price=round(price, 6))
        if order.side == OrderSide.BUY and order.market_low is not None:
            if order.market_low <= order.limit_price:
                return ExecutionResult(
                    status=OrderStatus.FILLED,
                    filled_price=min(order.reference_price, order.limit_price),
                )
        if order.side == OrderSide.SELL and order.market_high is not None:
            if order.market_high >= order.limit_price:
                return ExecutionResult(
                    status=OrderStatus.FILLED,
                    filled_price=max(order.reference_price, order.limit_price),
                )
        return ExecutionResult(status=OrderStatus.PENDING, reason="Limit price was not reached.")

    async def submit_order(self, order: OrderRequest) -> PaperOrder:
        result = self.match(order)
        row = PaperOrder(
            portfolio_id=order.portfolio_id,
            symbol=order.symbol.upper(),
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=order.quantity,
            limit_price=order.limit_price,
            signal_price=order.reference_price,
            filled_price=result.filled_price,
            status=result.status.value,
            execution_mode=TradingMode.INTERNAL_PAPER.value,
            market_session=order.market_session.value,
            filled_at=datetime.now(timezone.utc) if result.status == OrderStatus.FILLED else None,
            metadata_json={"reason": result.reason},
        )
        self.db.add(row)
        self.db.flush()
        if result.status == OrderStatus.FILLED:
            self._apply_fill(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _apply_fill(self, order: PaperOrder) -> None:
        portfolio = self.db.get(Portfolio, order.portfolio_id)
        if portfolio is None or order.filled_price is None:
            raise ValueError("Portfolio or fill price is missing.")
        position = self.db.scalar(
            select(PaperPosition).where(
                PaperPosition.portfolio_id == order.portfolio_id,
                PaperPosition.symbol == order.symbol,
            )
        )
        if position is None:
            position = PaperPosition(portfolio_id=order.portfolio_id, symbol=order.symbol)
            self.db.add(position)
            self.db.flush()
        amount = order.quantity * order.filled_price
        old_qty = position.quantity
        if order.side == OrderSide.BUY.value:
            if portfolio.cash < amount:
                raise ValueError("Insufficient paper cash.")
            new_qty = old_qty + order.quantity
            position.average_cost = (
                (old_qty * position.average_cost + amount) / new_qty if new_qty else 0
            )
            position.quantity = new_qty
            portfolio.cash -= amount
        else:
            if old_qty < order.quantity:
                raise ValueError("Insufficient paper position.")
            position.realized_pnl += order.quantity * (order.filled_price - position.average_cost)
            position.quantity = old_qty - order.quantity
            portfolio.cash += amount
            if position.quantity == 0:
                position.average_cost = 0
        position.market_price = order.filled_price
        position.market_value = position.quantity * order.filled_price
        position.unrealized_pnl = position.quantity * (order.filled_price - position.average_cost)
        portfolio.equity = portfolio.cash + sum(
            p.market_value
            for p in self.db.scalars(
                select(PaperPosition).where(PaperPosition.portfolio_id == portfolio.id)
            )
        )
        self.db.add(
            Trade(
                portfolio_id=portfolio.id,
                order_id=order.id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=order.filled_price,
                fees=0,
                slippage=abs(order.filled_price - order.signal_price),
                execution_mode=TradingMode.INTERNAL_PAPER.value,
            )
        )

    async def cancel_order(self, order_id: int) -> PaperOrder:
        row = self.db.get(PaperOrder, order_id)
        if row is None:
            raise KeyError(order_id)
        if row.status == OrderStatus.PENDING.value:
            row.status = OrderStatus.CANCELLED.value
            row.cancelled_at = datetime.now(timezone.utc)
            self.db.commit()
        return row

    async def get_order(self, order_id: int) -> Any:
        return self.db.get(PaperOrder, order_id)
