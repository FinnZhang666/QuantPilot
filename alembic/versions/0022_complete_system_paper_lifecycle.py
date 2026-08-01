"""complete the auditable system paper lifecycle

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


NEW_TABLES = (
    "system_paper_audit_events",
    "system_paper_scheduler_jobs",
    "system_paper_runtime_locks",
)


def _names(bind, table):
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    account = _names(bind, "system_paper_accounts")
    with op.batch_alter_table("system_paper_accounts") as batch:
        if "peak_equity" not in account:
            batch.add_column(sa.Column("peak_equity", sa.Numeric(24, 8), nullable=False, server_default="0"))
        if "max_drawdown" not in account:
            batch.add_column(sa.Column("max_drawdown", sa.Numeric(18, 8), nullable=False, server_default="0"))

    order = _names(bind, "system_paper_orders")
    with op.batch_alter_table("system_paper_orders") as batch:
        if "rejection_code" not in order:
            batch.add_column(sa.Column("rejection_code", sa.String(64), nullable=True))
        if "trigger_price" not in order:
            batch.add_column(sa.Column("trigger_price", sa.Numeric(24, 8), nullable=True))
        if "trigger_bar_timestamp" not in order:
            batch.add_column(sa.Column("trigger_bar_timestamp", sa.DateTime(timezone=True), nullable=True))
        if "rule_version" not in order:
            batch.add_column(sa.Column("rule_version", sa.String(32), nullable=False, server_default="paper-exit-v1"))

    position = _names(bind, "system_paper_positions")
    with op.batch_alter_table("system_paper_positions") as batch:
        definitions = (
            ("trade_style", sa.String(32), False, "PULLBACK"),
            ("timeframe", sa.String(8), False, "1d"),
            ("initial_quantity", sa.Numeric(24, 8), False, "0"),
            ("entry_bar_timestamp", sa.DateTime(timezone=True), True, None),
            ("fill_model_version", sa.String(32), False, "paper-fill-v1"),
            ("exit_rule_version", sa.String(32), False, "paper-exit-v1"),
            ("target_index", sa.Integer, False, "0"),
            ("bars_held", sa.Integer, False, "0"),
            ("last_market_timestamp", sa.DateTime(timezone=True), True, None),
            ("market_data_status", sa.String(16), False, "CURRENT"),
            ("data_quality", sa.String(16), False, "HIGH"),
            ("last_exit_trigger_price", sa.Numeric(24, 8), True, None),
            ("last_exit_trigger_bar", sa.DateTime(timezone=True), True, None),
        )
        for name, kind, nullable, default in definitions:
            if name not in position:
                kwargs = {"nullable": nullable}
                if default is not None:
                    kwargs["server_default"] = default
                batch.add_column(sa.Column(name, kind, **kwargs))

    snapshot = _names(bind, "system_equity_snapshots")
    with op.batch_alter_table("system_equity_snapshots") as batch:
        definitions = (
            ("daily_return", sa.Numeric(18, 8), "0"),
            ("cumulative_return", sa.Numeric(18, 8), "0"),
            ("peak_equity", sa.Numeric(24, 8), "0"),
            ("max_drawdown", sa.Numeric(18, 8), "0"),
            ("source", sa.String(32), "RUNTIME_VALUATION"),
        )
        for name, kind, default in definitions:
            if name not in snapshot:
                batch.add_column(sa.Column(name, kind, nullable=False, server_default=default))

    review = _names(bind, "trade_reviews")
    with op.batch_alter_table("trade_reviews") as batch:
        if "system_paper_position_id" not in review:
            batch.add_column(sa.Column("system_paper_position_id", sa.Integer, nullable=True))
            batch.create_foreign_key(
                "fk_trade_review_system_paper_position",
                "system_paper_positions", ["system_paper_position_id"], ["id"],
            )
            batch.create_index(
                "ix_trade_reviews_system_paper_position", ["system_paper_position_id"], unique=False,
            )
        definitions = (
            ("realized_return", sa.Numeric(18, 8)),
            ("exit_reason", sa.String(64)),
            ("strategy_name", sa.String(128)),
            ("strategy_version", sa.String(64)),
            ("fill_model_version", sa.String(32)),
            ("data_quality", sa.String(16)),
        )
        for name, kind in definitions:
            if name not in review:
                batch.add_column(sa.Column(name, kind, nullable=True))
        if "source_snapshot_json" not in review:
            batch.add_column(sa.Column("source_snapshot_json", sa.JSON, nullable=False, server_default="{}"))

    for name in NEW_TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)

    review = _names(bind, "trade_reviews")
    review_indexes = sa.inspect(bind).get_indexes("trade_reviews")
    for item in review_indexes:
        if "system_paper_position_id" in (item.get("column_names") or []):
            op.drop_index(item["name"], table_name="trade_reviews")
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    }
    with op.batch_alter_table(
        "trade_reviews", naming_convention=naming_convention,
    ) as batch:
        if "system_paper_position_id" in review:
            batch.drop_constraint(
                "fk_trade_reviews_system_paper_position_id_system_paper_positions",
                type_="foreignkey",
            )
        for name in (
            "source_snapshot_json", "data_quality", "fill_model_version",
            "strategy_version", "strategy_name", "exit_reason", "realized_return",
            "system_paper_position_id",
        ):
            if name in review:
                batch.drop_column(name)

    columns = {
        "system_equity_snapshots": (
            "source", "max_drawdown", "peak_equity", "cumulative_return", "daily_return",
        ),
        "system_paper_positions": (
            "last_exit_trigger_bar", "last_exit_trigger_price", "data_quality",
            "market_data_status", "last_market_timestamp", "bars_held", "target_index",
            "exit_rule_version", "fill_model_version", "entry_bar_timestamp",
            "initial_quantity", "timeframe", "trade_style",
        ),
        "system_paper_orders": (
            "rule_version", "trigger_bar_timestamp", "trigger_price", "rejection_code",
        ),
        "system_paper_accounts": ("max_drawdown", "peak_equity"),
    }
    for table, names in columns.items():
        existing = _names(bind, table)
        with op.batch_alter_table(table) as batch:
            for name in names:
                if name in existing:
                    batch.drop_column(name)
