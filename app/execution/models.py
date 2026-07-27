from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.core.enums import MarketSession, OrderSide, OrderStatus, OrderType


class OrderRequest(BaseModel):
    portfolio_id: int
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0)
    reference_price: float = Field(gt=0)
    limit_price: Optional[float] = Field(default=None, gt=0)
    market_low: Optional[float] = Field(default=None, gt=0)
    market_high: Optional[float] = Field(default=None, gt=0)
    market_session: MarketSession = MarketSession.REGULAR

    @model_validator(mode="after")
    def limit_orders_need_price(self) -> "OrderRequest":
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT orders require limit_price.")
        return self


class ExecutionResult(BaseModel):
    status: OrderStatus
    filled_price: Optional[float] = None
    reason: str = ""
