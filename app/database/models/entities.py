from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    BigInteger,
    Numeric,
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


class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("market", "code", name="uq_instrument_market_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    market: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(32))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    alias: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    security_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    support_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    support_message: Mapped[str] = mapped_column(String(255), default="待确认")


class MarketBar(TimestampMixin, Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "interval",
            "timestamp_utc",
            "adjustment_type",
            "data_source",
            name="uq_market_bar_identity",
        ),
        Index("ix_market_bars_symbol_interval_time", "symbol", "interval", "timestamp_utc"),
        Index("ix_market_bars_instrument_interval_time", "instrument_id", "interval", "timestamp_utc"),
        Index("ix_market_bars_trading_date", "trading_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    interval: Mapped[str] = mapped_column(String(8))
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timestamp_market: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trading_date: Mapped[str] = mapped_column(String(10))
    open: Mapped[object] = mapped_column(Numeric(24, 8))
    high: Mapped[object] = mapped_column(Numeric(24, 8))
    low: Mapped[object] = mapped_column(Numeric(24, 8))
    close: Mapped[object] = mapped_column(Numeric(24, 8))
    volume: Mapped[int] = mapped_column(BigInteger)
    turnover: Mapped[Optional[object]] = mapped_column(Numeric(28, 8))
    change_rate: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    last_close: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    is_blank: Mapped[bool] = mapped_column(Boolean, default=False)
    market_session: Mapped[str] = mapped_column(String(32))
    adjustment_type: Mapped[str] = mapped_column(String(16))
    data_source: Mapped[str] = mapped_column(String(32), default="MOOMOO")


class HistorySyncJob(Base):
    __tablename__ = "history_sync_jobs"
    __table_args__ = (Index("ix_history_jobs_symbol_interval", "symbol", "interval"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    interval: Mapped[str] = mapped_column(String(8))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    adjustment_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rows_received: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    pages_requested: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[Optional[str]] = mapped_column(String(32))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HistoryDataIssue(Base):
    __tablename__ = "history_data_issues"
    __table_args__ = (
        Index("ix_history_issues_symbol_interval", "symbol", "interval"),
        Index("ix_history_issues_issue_type", "issue_type"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    interval: Mapped[str] = mapped_column(String(8))
    timestamp_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    issue_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="WARNING")
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RealtimeQuote(TimestampMixin, Base):
    __tablename__ = "realtime_quotes"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp_utc", "data_source", name="uq_realtime_quote_identity"),
        Index("ix_realtime_quotes_symbol_time", "symbol", "timestamp_utc"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timestamp_market: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timestamp_beijing: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_price: Mapped[object] = mapped_column(Numeric(24, 8))
    open_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    high_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    low_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    prev_close: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    turnover: Mapped[Optional[object]] = mapped_column(Numeric(28, 8))
    amplitude: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    turnover_rate: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    bid_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    ask_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    bid_volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    ask_volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    market_session: Mapped[str] = mapped_column(String(32))
    market_status: Mapped[Optional[str]] = mapped_column(String(64))
    data_source: Mapped[str] = mapped_column(String(32), default="MOOMOO")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RealtimeTicker(Base):
    __tablename__ = "realtime_tickers"
    __table_args__ = (
        UniqueConstraint("symbol", "sequence", "ticker_time_utc", "data_source", name="uq_realtime_ticker_identity"),
        Index("ix_realtime_tickers_symbol_time", "symbol", "ticker_time_utc"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    ticker_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ticker_time_market: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price: Mapped[object] = mapped_column(Numeric(24, 8))
    volume: Mapped[int] = mapped_column(BigInteger)
    turnover: Mapped[Optional[object]] = mapped_column(Numeric(28, 8))
    direction: Mapped[Optional[str]] = mapped_column(String(32))
    sequence: Mapped[str] = mapped_column(String(96))
    market_session: Mapped[str] = mapped_column(String(32))
    data_source: Mapped[str] = mapped_column(String(32), default="MOOMOO")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RealtimeBar(TimestampMixin, Base):
    __tablename__ = "realtime_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "timestamp_utc", "data_source", name="uq_realtime_bar_identity"),
        Index("ix_realtime_bars_symbol_interval_time", "symbol", "interval", "timestamp_utc"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    interval: Mapped[str] = mapped_column(String(8), default="1m")
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timestamp_market: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trading_date: Mapped[str] = mapped_column(String(10))
    open: Mapped[object] = mapped_column(Numeric(24, 8))
    high: Mapped[object] = mapped_column(Numeric(24, 8))
    low: Mapped[object] = mapped_column(Numeric(24, 8))
    close: Mapped[object] = mapped_column(Numeric(24, 8))
    volume: Mapped[int] = mapped_column(BigInteger)
    turnover: Mapped[Optional[object]] = mapped_column(Numeric(28, 8))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    market_session: Mapped[str] = mapped_column(String(32))
    data_source: Mapped[str] = mapped_column(String(32), default="MOOMOO")


class RealtimeServiceStatus(TimestampMixin, Base):
    __tablename__ = "realtime_service_status"
    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(64), unique=True, default="moomoo_realtime")
    status: Mapped[str] = mapped_column(String(32), default="STOPPED")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_disconnected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_quote_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_ticker_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_bar_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    connection_count: Mapped[int] = mapped_column(Integer, default=0)
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0)
    subscribed_symbols_json: Mapped[list] = mapped_column(JSON, default=list)
    subscribed_types_json: Mapped[list] = mapped_column(JSON, default=list)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class MarketSessionEvent(Base):
    __tablename__ = "market_session_events"
    __table_args__ = (Index("ix_market_session_events_market_time", "market", "event_time_utc"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(16), default="US")
    previous_session: Mapped[str] = mapped_column(String(32))
    current_session: Mapped[str] = mapped_column(String(32))
    source_status: Mapped[Optional[str]] = mapped_column(String(64))
    event_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_time_market: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeatureDefinitionRecord(TimestampMixin, Base):
    __tablename__ = "feature_definitions"
    __table_args__ = (UniqueConstraint("feature_name", "version", name="uq_feature_definition_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    feature_name: Mapped[str] = mapped_column(String(96))
    display_name_zh: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(16))
    default_parameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    required_bars: Mapped[int] = mapped_column(Integer)
    supported_intervals_json: Mapped[list] = mapped_column(JSON, default=list)
    requires_reference_symbol: Mapped[bool] = mapped_column(Boolean, default=False)
    reference_symbol: Mapped[Optional[str]] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(16), default="1.0.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FeatureValueRecord(TimestampMixin, Base):
    __tablename__ = "feature_values"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "timestamp_utc", "feature_name", "feature_version", "parameters_hash", "data_source", name="uq_feature_value_identity"),
        Index("ix_feature_values_symbol_interval_time", "symbol", "interval", "timestamp_utc"),
        Index("ix_feature_values_name_time", "feature_name", "timestamp_utc"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    interval: Mapped[str] = mapped_column(String(8))
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    feature_name: Mapped[str] = mapped_column(String(96))
    feature_version: Mapped[str] = mapped_column(String(16))
    parameters_hash: Mapped[str] = mapped_column(String(64))
    value_decimal: Mapped[Optional[object]] = mapped_column(Numeric(30, 12))
    value_integer: Mapped[Optional[int]] = mapped_column(BigInteger)
    value_boolean: Mapped[Optional[bool]] = mapped_column(Boolean)
    value_text: Mapped[Optional[str]] = mapped_column(String(128))
    quality_status: Mapped[str] = mapped_column(String(16))
    quality_message: Mapped[Optional[str]] = mapped_column(Text)
    source_bar_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_source: Mapped[str] = mapped_column(String(32))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeatureCalculationJob(Base):
    __tablename__ = "feature_calculation_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    job_type: Mapped[str] = mapped_column(String(16))
    symbols_json: Mapped[list] = mapped_column(JSON, default=list)
    intervals_json: Mapped[list] = mapped_column(JSON, default=list)
    feature_names_json: Mapped[list] = mapped_column(JSON, default=list)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    input_rows: Mapped[int] = mapped_column(Integer, default=0)
    output_rows: Mapped[int] = mapped_column(Integer, default=0)
    inserted_rows: Mapped[int] = mapped_column(Integer, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_features: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeatureQualityIssue(Base):
    __tablename__ = "feature_quality_issues"
    __table_args__ = (Index("ix_feature_issues_symbol_name", "symbol", "feature_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    interval: Mapped[str] = mapped_column(String(8))
    timestamp_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    feature_name: Mapped[str] = mapped_column(String(96))
    feature_version: Mapped[str] = mapped_column(String(16))
    issue_type: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WatchlistItem(TimestampMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("symbol", "market", name="uq_watchlist_symbol_market"),
        Index("ix_watchlist_enabled", "enabled"),
        Index("ix_watchlist_role", "role"),
        Index("ix_watchlist_validation", "validation_status"),
        Index("ix_watchlist_benchmark", "benchmark_symbol"),
        Index("ix_watchlist_classification", "classification_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(16), default="US")
    display_name: Mapped[str] = mapped_column(String(128), default="")
    asset_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    sector: Mapped[str] = mapped_column(String(64), default="unknown")
    role: Mapped[str] = mapped_column(String(32))
    benchmark_symbol: Mapped[Optional[str]] = mapped_column(String(32))
    strategy_template: Mapped[str] = mapped_column(String(48))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="PENDING_VALIDATION")
    validation_message: Mapped[str] = mapped_column(Text, default="")
    classification_source: Mapped[str] = mapped_column(String(16), default="AUTO")
    notes: Mapped[Optional[str]] = mapped_column(Text)


class WatchlistTimeframe(TimestampMixin, Base):
    __tablename__ = "watchlist_timeframes"
    __table_args__ = (
        UniqueConstraint("watchlist_item_id", "timeframe", name="uq_watchlist_timeframe"),
        Index("ix_watchlist_timeframe_enabled", "watchlist_item_id", "enabled"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_item_id: Mapped[int] = mapped_column(ForeignKey("watchlist_items.id"))
    timeframe: Mapped[str] = mapped_column(String(8))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class StrategyParameterSet(TimestampMixin, Base):
    __tablename__ = "strategy_parameter_sets"
    __table_args__ = (
        UniqueConstraint("watchlist_item_id", "strategy_name", "strategy_version", name="uq_strategy_parameter_set"),
        Index("ix_strategy_parameter_enabled", "watchlist_item_id", "enabled"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_item_id: Mapped[int] = mapped_column(ForeignKey("watchlist_items.id"))
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(16))
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    parameters_hash: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class CandidateSignal(TimestampMixin, Base):
    __tablename__ = "candidate_signals"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "market", "timeframe", "bar_timestamp", "strategy_name",
            "strategy_version", "parameters_hash", name="uq_candidate_signal_identity",
        ),
        Index("ix_candidate_signal_symbol_time", "symbol", "timeframe", "bar_timestamp"),
        Index("ix_candidate_signal_type", "signal_type"),
        Index("ix_candidate_signal_score", "score"),
        Index("ix_candidate_signal_confidence", "confidence"),
        Index("ix_candidate_signal_created", "created_at"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_candidate_signal_score"),
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_candidate_signal_confidence"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(16), default="US")
    timeframe: Mapped[str] = mapped_column(String(8))
    bar_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(16))
    parameters_hash: Mapped[str] = mapped_column(String(64))
    signal_type: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    summary_zh: Mapped[str] = mapped_column(Text)
    reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    risks_json: Mapped[list] = mapped_column(JSON, default=list)
    feature_refs_json: Mapped[dict] = mapped_column(JSON, default=dict)
    components_json: Mapped[dict] = mapped_column(JSON, default=dict)


class StrategyRun(TimestampMixin, Base):
    __tablename__ = "strategy_runs"
    __table_args__ = (
        Index("ix_strategy_runs_status", "status"),
        Index("ix_strategy_runs_type", "run_type"),
        Index("ix_strategy_runs_started", "started_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    run_type: Mapped[str] = mapped_column(String(16))
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(16))
    symbols_json: Mapped[list] = mapped_column(JSON, default=list)
    timeframes_json: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    bars_evaluated: Mapped[int] = mapped_column(Integer, default=0)
    signals_written: Mapped[int] = mapped_column(Integer, default=0)
    signals_skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0)
    free_disk_gb: Mapped[float] = mapped_column(Float, default=0)
    error_summary: Mapped[dict] = mapped_column(JSON, default=dict)
