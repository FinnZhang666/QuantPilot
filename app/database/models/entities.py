from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StrategyRecord(TimestampMixin, Base):
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32), default="0.1.0")
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Portfolio(TimestampMixin, Base):
    __tablename__ = "portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    initial_cash: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    strategy_code: Mapped[Optional[str]] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy_code: Mapped[str] = mapped_column(String(64), index=True)
    strategy_version: Mapped[str] = mapped_column(String(32))
    signal_type: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    market_session: Mapped[str] = mapped_column(String(32))
    reference_price: Mapped[float] = mapped_column(Float)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="NEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        CheckConstraint(
            "execution_mode IN ('INTERNAL_PAPER','MOOMOO_PAPER')",
            name="ck_paper_orders_execution_mode",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float)
    limit_price: Mapped[Optional[float]] = mapped_column(Float)
    signal_price: Mapped[float] = mapped_column(Float)
    filled_price: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    execution_mode: Mapped[str] = mapped_column(String(32))
    market_session: Mapped[str] = mapped_column(String(32))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "symbol", name="uq_position_portfolio_symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[float] = mapped_column(Float, default=0)
    average_cost: Mapped[float] = mapped_column(Float, default=0)
    market_price: Mapped[float] = mapped_column(Float, default=0)
    market_value: Mapped[float] = mapped_column(Float, default=0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(
            "execution_mode IN ('INTERNAL_PAPER','MOOMOO_PAPER')",
            name="ck_trades_execution_mode",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    order_id: Mapped[int] = mapped_column(ForeignKey("paper_orders.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0)
    slippage: Mapped[float] = mapped_column(Float, default=0)
    trade_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    execution_mode: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemEvent(Base):
    __tablename__ = "system_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(16))
    component: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MoomooConnectionCheck(Base):
    __tablename__ = "moomoo_connection_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    opend_reachable: Mapped[bool] = mapped_column(Boolean, default=False)
    opend_logged_in: Mapped[bool] = mapped_column(Boolean, default=False)
    sdk_version: Mapped[str] = mapped_column(String(32), default="")
    opend_version: Mapped[str] = mapped_column(String(32), default="")
    quote_capabilities_json: Mapped[dict] = mapped_column(JSON, default=dict)
    paper_account_found: Mapped[bool] = mapped_column(Boolean, default=False)
    live_account_found: Mapped[bool] = mapped_column(Boolean, default=False)
    errors_json: Mapped[list] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    status_code: Mapped[str] = mapped_column(String(32), default="not_checked")
    status_message_zh: Mapped[str] = mapped_column(String(255), default="尚未检查")
