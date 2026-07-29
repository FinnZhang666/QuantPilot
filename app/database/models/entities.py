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


class BacktestRun(TimestampMixin, Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        Index("ix_backtest_runs_symbol_timeframe", "symbol", "timeframe"),
        Index("ix_backtest_runs_status", "status"),
        Index("ix_backtest_runs_configuration_hash", "configuration_hash"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_name: Mapped[str] = mapped_column(String(128))
    run_mode: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(16), default="US")
    timeframe: Mapped[str] = mapped_column(String(8))
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(16))
    parameters_hash: Mapped[str] = mapped_column(String(64))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    warmup_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    initial_cash: Mapped[object] = mapped_column(Numeric(24, 8))
    ending_cash: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    ending_equity: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    position_sizing_mode: Mapped[str] = mapped_column(String(24), default="FULL_CASH")
    execution_mode: Mapped[str] = mapped_column(String(32), default="NEXT_BAR_OPEN")
    commission_per_trade: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    commission_per_share: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    minimum_commission: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    slippage_bps: Mapped[object] = mapped_column(Numeric(12, 4), default=0)
    force_close_at_end: Mapped[bool] = mapped_column(Boolean, default=True)
    benchmark_symbol: Mapped[Optional[str]] = mapped_column(String(32))
    benchmark_status: Mapped[str] = mapped_column(String(32), default="UNAVAILABLE")
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    bars_processed: Mapped[int] = mapped_column(Integer, default=0)
    signals_processed: Mapped[int] = mapped_column(Integer, default=0)
    entries_count: Mapped[int] = mapped_column(Integer, default=0)
    exits_count: Mapped[int] = mapped_column(Integer, default=0)
    forced_exit_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_trades_count: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    gross_profit: Mapped[object] = mapped_column(Numeric(24, 8), default=0)
    gross_loss: Mapped[object] = mapped_column(Numeric(24, 8), default=0)
    gross_pnl: Mapped[object] = mapped_column(Numeric(24, 8), default=0)
    net_pnl: Mapped[object] = mapped_column(Numeric(24, 8), default=0)
    total_return_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    annualized_return_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    max_drawdown_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    win_rate: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    profit_factor: Mapped[Optional[object]] = mapped_column(Numeric(24, 10))
    average_trade_return_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    average_holding_bars: Mapped[Optional[object]] = mapped_column(Numeric(18, 4))
    average_holding_seconds: Mapped[Optional[object]] = mapped_column(Numeric(24, 4))
    symbol_buy_hold_return_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    benchmark_return_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    excess_return_vs_symbol_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    excess_return_vs_benchmark_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    open_position: Mapped[bool] = mapped_column(Boolean, default=False)
    unrealized_pnl: Mapped[object] = mapped_column(Numeric(24, 8), default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[float] = mapped_column(Float, default=0)
    error_summary: Mapped[dict] = mapped_column(JSON, default=dict)


class BacktestTrade(TimestampMixin, Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        UniqueConstraint("backtest_run_id", "trade_number", name="uq_backtest_trade_number"),
        Index("ix_backtest_trades_symbol_timeframe", "symbol", "timeframe"),
        Index("ix_backtest_trades_entry_time", "entry_execution_timestamp"),
        Index("ix_backtest_trades_exit_time", "exit_execution_timestamp"),
        Index("ix_backtest_trades_status", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"), index=True)
    trade_number: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(24))
    entry_signal_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_execution_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_signal_type: Mapped[str] = mapped_column(String(32))
    entry_raw_price: Mapped[object] = mapped_column(Numeric(24, 8))
    entry_adjusted_price: Mapped[object] = mapped_column(Numeric(24, 8))
    entry_shares: Mapped[int] = mapped_column(BigInteger)
    entry_notional: Mapped[object] = mapped_column(Numeric(24, 8))
    entry_fees: Mapped[object] = mapped_column(Numeric(18, 8))
    exit_signal_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    exit_execution_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    exit_signal_type: Mapped[Optional[str]] = mapped_column(String(32))
    exit_reason: Mapped[Optional[str]] = mapped_column(String(64))
    exit_raw_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    exit_adjusted_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    exit_notional: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    exit_fees: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    gross_pnl: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    net_pnl: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    return_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    holding_bars: Mapped[Optional[int]] = mapped_column(Integer)
    holding_seconds: Mapped[Optional[int]] = mapped_column(BigInteger)
    mae_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))
    mfe_pct: Mapped[Optional[object]] = mapped_column(Numeric(18, 10))


class BacktestEquityPoint(Base):
    __tablename__ = "backtest_equity_points"
    __table_args__ = (
        UniqueConstraint("backtest_run_id", "timestamp", name="uq_backtest_equity_time"),
        Index("ix_backtest_equity_run_time", "backtest_run_id", "timestamp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cash: Mapped[object] = mapped_column(Numeric(24, 8))
    position_shares: Mapped[int] = mapped_column(BigInteger)
    position_market_value: Mapped[object] = mapped_column(Numeric(24, 8))
    equity: Mapped[object] = mapped_column(Numeric(24, 8))
    running_peak: Mapped[object] = mapped_column(Numeric(24, 8))
    drawdown_amount: Mapped[object] = mapped_column(Numeric(24, 8))
    drawdown_pct: Mapped[object] = mapped_column(Numeric(18, 10))
    signal_type: Mapped[Optional[str]] = mapped_column(String(32))
    position_state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestPendingAction(TimestampMixin, Base):
    __tablename__ = "backtest_pending_actions"
    __table_args__ = (Index("ix_backtest_pending_run_status", "backtest_run_id", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    action_type: Mapped[str] = mapped_column(String(32))
    signal_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_type: Mapped[str] = mapped_column(String(32))
    scheduled_execution_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    execution_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "strategy_name", "strategy_version",
            "direction", "bar_time", name="uq_opportunity_identity",
        ),
        Index("ix_opportunities_symbol_time", "symbol", "bar_time"),
        Index("ix_opportunities_status_detected", "status", "detected_at"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_opportunity_score"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_opportunity_confidence",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    direction: Mapped[str] = mapped_column(String(8))
    opportunity_type: Mapped[str] = mapped_column(String(48))
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(16))
    signal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("candidate_signals.id"))
    market_regime: Mapped[Optional[str]] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24), default="DETECTED")
    score: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[Optional[int]] = mapped_column(Integer)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_reference_price: Mapped[object] = mapped_column(Numeric(24, 8))
    stop_reference_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    target_reference_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    expiry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    feature_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    strategy_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON)
    notification_status: Mapped[str] = mapped_column(String(24), default="PENDING")
    notification_message_id: Mapped[Optional[str]] = mapped_column(String(64))
    candidate_pool_entry_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("candidate_pool_entries.id")
    )
    market_regime_id: Mapped[Optional[int]] = mapped_column(ForeignKey("market_regimes.id"))


class RuntimeStatus(TimestampMixin, Base):
    __tablename__ = "runtime_status"
    __table_args__ = (Index("ix_runtime_status_status", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="STOPPED")
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DevelopmentIssue(TimestampMixin, Base):
    __tablename__ = "development_issues"
    __table_args__ = (
        Index("ix_development_issues_status", "status"),
        Index("ix_development_issues_source", "source_type"),
        Index("ix_development_issues_priority", "priority"),
        Index("ix_development_issues_created", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32))
    source_reference: Mapped[Optional[str]] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64))
    priority: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="INBOX")
    evidence_json: Mapped[Optional[dict]] = mapped_column(JSON)
    ai_recommendation: Mapped[Optional[str]] = mapped_column(Text)
    codex_prompt: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(128))
    approved_by: Mapped[Optional[str]] = mapped_column(String(128))


class MarketRegime(TimestampMixin, Base):
    __tablename__ = "market_regimes"
    __table_args__ = (
        UniqueConstraint("market", "timeframe", "bar_time", name="uq_market_regime_bar"),
        Index("ix_market_regimes_market_time", "market", "timeframe", "bar_time"),
        Index("ix_market_regimes_regime", "regime"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(16), default="US")
    timeframe: Mapped[str] = mapped_column(String(8), default="1d")
    regime: Mapped[str] = mapped_column(String(24))
    trend_score: Mapped[int] = mapped_column(Integer)
    breadth_score: Mapped[Optional[int]] = mapped_column(Integer)
    momentum_score: Mapped[int] = mapped_column(Integer)
    volatility_score: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[int] = mapped_column(Integer)
    long_bias: Mapped[int] = mapped_column(Integer)
    short_bias: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[int] = mapped_column(Integer)
    benchmark_symbol: Mapped[str] = mapped_column(String(32))
    sector_benchmark_symbol: Mapped[Optional[str]] = mapped_column(String(32))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    bar_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    feature_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reason_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CandidatePoolRun(TimestampMixin, Base):
    __tablename__ = "candidate_pool_runs"
    __table_args__ = (
        Index("ix_candidate_pool_runs_status", "status"),
        Index("ix_candidate_pool_runs_started", "started_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(16))
    market: Mapped[str] = mapped_column(String(16), default="US")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="RUNNING")
    universe_size: Mapped[int] = mapped_column(Integer, default=0)
    scanned_size: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    long_count: Mapped[int] = mapped_column(Integer, default=0)
    short_count: Mapped[int] = mapped_column(Integer, default=0)
    both_count: Mapped[int] = mapped_column(Integer, default=0)
    regime_id: Mapped[Optional[int]] = mapped_column(ForeignKey("market_regimes.id"))
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CandidatePoolEntry(TimestampMixin, Base):
    __tablename__ = "candidate_pool_entries"
    __table_args__ = (
        UniqueConstraint("symbol", "market", "pool_date", name="uq_candidate_pool_daily_symbol"),
        Index("ix_candidate_pool_date_rank", "pool_date", "rank"),
        Index("ix_candidate_pool_direction_status", "direction", "status"),
        Index("ix_candidate_pool_symbol_seen", "symbol", "last_seen_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(16), default="US")
    asset_type: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    direction: Mapped[str] = mapped_column(String(8))
    source_type: Mapped[str] = mapped_column(String(32))
    source_reference: Mapped[Optional[str]] = mapped_column(String(255))
    pool_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), default="CANDIDATE")
    long_score: Mapped[int] = mapped_column(Integer)
    short_score: Mapped[int] = mapped_column(Integer)
    final_score: Mapped[int] = mapped_column(Integer)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    market_regime_id: Mapped[Optional[int]] = mapped_column(ForeignKey("market_regimes.id"))
    benchmark_symbol: Mapped[str] = mapped_column(String(32))
    sector_benchmark_symbol: Mapped[Optional[str]] = mapped_column(String(32))
    reason_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    filter_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OpportunityReview(TimestampMixin, Base):
    __tablename__ = "opportunity_reviews"
    __table_args__ = (
        UniqueConstraint("opportunity_id", name="uq_opportunity_review_final"),
        Index("ix_opportunity_reviews_status_time", "review_status", "review_time"),
        Index("ix_opportunity_reviews_window", "review_window"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id"))
    review_status: Mapped[str] = mapped_column(String(24))
    review_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    holding_bars: Mapped[int] = mapped_column(Integer, default=0)
    holding_minutes: Mapped[int] = mapped_column(Integer, default=0)
    holding_days: Mapped[object] = mapped_column(Numeric(16, 6), default=0)
    entry_reference_price: Mapped[object] = mapped_column(Numeric(24, 8))
    exit_reference_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    last_price: Mapped[Optional[object]] = mapped_column(Numeric(24, 8))
    mfe_percent: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    mae_percent: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    return_percent: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    max_close_return: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    min_close_return: Mapped[Optional[object]] = mapped_column(Numeric(18, 8))
    target_hit: Mapped[Optional[bool]] = mapped_column(Boolean)
    stop_hit: Mapped[Optional[bool]] = mapped_column(Boolean)
    expired: Mapped[bool] = mapped_column(Boolean, default=False)
    review_window: Mapped[str] = mapped_column(String(16))
    price_path_json: Mapped[list] = mapped_column(JSON, default=list)
    statistics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reason_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ReviewStatistic(TimestampMixin, Base):
    __tablename__ = "review_statistics"
    __table_args__ = (
        UniqueConstraint(
            "strategy_name", "strategy_version", "timeframe", "symbol",
            name="uq_review_statistics_group",
        ),
        Index("ix_review_statistics_strategy", "strategy_name", "timeframe"),
        Index("ix_review_statistics_symbol", "symbol"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(16))
    timeframe: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(32))
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    long_count: Mapped[int] = mapped_column(Integer, default=0)
    short_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    average_return: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    average_mfe: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    average_mae: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    maximum_return: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    maximum_drawdown: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    review_coverage_rate: Mapped[object] = mapped_column(Numeric(18, 8), default=0)
    data_insufficient_count: Mapped[int] = mapped_column(Integer, default=0)
