"""Add historical market data warehouse."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("market", sa.String(16), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("alias", sa.String(64)),
        sa.Column("security_type", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_supported", sa.Boolean(), nullable=False),
        sa.Column("support_status", sa.String(32), nullable=False),
        sa.Column("support_message", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("market", "code", name="uq_instrument_market_code"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])
    op.create_index("ix_instruments_market", "instruments", ["market"])
    op.create_index("ix_instruments_alias", "instruments", ["alias"])
    op.create_table(
        "market_bars",
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
        sa.Column("change_rate", sa.Numeric(18, 8)),
        sa.Column("last_close", sa.Numeric(24, 8)),
        sa.Column("is_blank", sa.Boolean(), nullable=False),
        sa.Column("market_session", sa.String(32), nullable=False),
        sa.Column("adjustment_type", sa.String(16), nullable=False),
        sa.Column("data_source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "symbol", "interval", "timestamp_utc", "adjustment_type", "data_source",
            name="uq_market_bar_identity",
        ),
    )
    op.create_index("ix_market_bars_symbol_interval_time", "market_bars", ["symbol", "interval", "timestamp_utc"])
    op.create_index("ix_market_bars_instrument_interval_time", "market_bars", ["instrument_id", "interval", "timestamp_utc"])
    op.create_index("ix_market_bars_trading_date", "market_bars", ["trading_date"])
    op.create_table(
        "history_sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False, unique=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("adjustment_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("rows_received", sa.Integer(), nullable=False),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("rows_updated", sa.Integer(), nullable=False),
        sa.Column("rows_skipped", sa.Integer(), nullable=False),
        sa.Column("pages_requested", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_history_sync_jobs_job_id", "history_sync_jobs", ["job_id"])
    op.create_index("ix_history_sync_jobs_status", "history_sync_jobs", ["status"])
    op.create_index("ix_history_jobs_symbol_interval", "history_sync_jobs", ["symbol", "interval"])
    op.create_table(
        "history_data_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True)),
        sa.Column("issue_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_history_issues_symbol_interval", "history_data_issues", ["symbol", "interval"])
    op.create_index("ix_history_issues_issue_type", "history_data_issues", ["issue_type"])


def downgrade():
    op.drop_table("history_data_issues")
    op.drop_table("history_sync_jobs")
    op.drop_table("market_bars")
    op.drop_table("instruments")
