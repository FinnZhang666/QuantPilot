"""add realtime market data

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "realtime_quotes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_market", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_beijing", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("open_price", sa.Numeric(24, 8)),
        sa.Column("high_price", sa.Numeric(24, 8)),
        sa.Column("low_price", sa.Numeric(24, 8)),
        sa.Column("prev_close", sa.Numeric(24, 8)),
        sa.Column("volume", sa.BigInteger()),
        sa.Column("turnover", sa.Numeric(28, 8)),
        sa.Column("amplitude", sa.Numeric(18, 8)),
        sa.Column("turnover_rate", sa.Numeric(18, 8)),
        sa.Column("bid_price", sa.Numeric(24, 8)),
        sa.Column("ask_price", sa.Numeric(24, 8)),
        sa.Column("bid_volume", sa.BigInteger()),
        sa.Column("ask_volume", sa.BigInteger()),
        sa.Column("market_session", sa.String(32), nullable=False),
        sa.Column("market_status", sa.String(64)),
        sa.Column("data_source", sa.String(32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "timestamp_utc", "data_source", name="uq_realtime_quote_identity"),
    )
    op.create_index("ix_realtime_quotes_symbol_time", "realtime_quotes", ["symbol", "timestamp_utc"])
    op.create_table(
        "realtime_tickers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("ticker_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ticker_time_market", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("turnover", sa.Numeric(28, 8)),
        sa.Column("direction", sa.String(32)),
        sa.Column("sequence", sa.String(96), nullable=False),
        sa.Column("market_session", sa.String(32), nullable=False),
        sa.Column("data_source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "sequence", "ticker_time_utc", "data_source", name="uq_realtime_ticker_identity"),
    )
    op.create_index("ix_realtime_tickers_symbol_time", "realtime_tickers", ["symbol", "ticker_time_utc"])
    op.create_table(
        "realtime_bars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_market", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trading_date", sa.String(10), nullable=False),
        sa.Column("open", sa.Numeric(24, 8), nullable=False),
        sa.Column("high", sa.Numeric(24, 8), nullable=False),
        sa.Column("low", sa.Numeric(24, 8), nullable=False),
        sa.Column("close", sa.Numeric(24, 8), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("turnover", sa.Numeric(28, 8)),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("market_session", sa.String(32), nullable=False),
        sa.Column("data_source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "interval", "timestamp_utc", "data_source", name="uq_realtime_bar_identity"),
    )
    op.create_index("ix_realtime_bars_symbol_interval_time", "realtime_bars", ["symbol", "interval", "timestamp_utc"])
    op.create_table(
        "realtime_service_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_name", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("last_connected_at", sa.DateTime(timezone=True)),
        sa.Column("last_disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("last_quote_at", sa.DateTime(timezone=True)),
        sa.Column("last_ticker_at", sa.DateTime(timezone=True)),
        sa.Column("last_bar_at", sa.DateTime(timezone=True)),
        sa.Column("connection_count", sa.Integer(), nullable=False),
        sa.Column("reconnect_count", sa.Integer(), nullable=False),
        sa.Column("subscribed_symbols_json", sa.JSON(), nullable=False),
        sa.Column("subscribed_types_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "market_session_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market", sa.String(16), nullable=False),
        sa.Column("previous_session", sa.String(32), nullable=False),
        sa.Column("current_session", sa.String(32), nullable=False),
        sa.Column("source_status", sa.String(64)),
        sa.Column("event_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_time_market", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_market_session_events_market_time", "market_session_events", ["market", "event_time_utc"])


def downgrade() -> None:
    op.drop_index("ix_market_session_events_market_time", table_name="market_session_events")
    op.drop_table("market_session_events")
    op.drop_table("realtime_service_status")
    op.drop_index("ix_realtime_bars_symbol_interval_time", table_name="realtime_bars")
    op.drop_table("realtime_bars")
    op.drop_index("ix_realtime_tickers_symbol_time", table_name="realtime_tickers")
    op.drop_table("realtime_tickers")
    op.drop_index("ix_realtime_quotes_symbol_time", table_name="realtime_quotes")
    op.drop_table("realtime_quotes")
