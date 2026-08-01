"""link system paper position to its closing order

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _has_column(bind):
    return "closing_order_id" in {
        row["name"] for row in sa.inspect(bind).get_columns("system_paper_positions")
    }


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind):
        with op.batch_alter_table("system_paper_positions") as batch:
            batch.add_column(sa.Column(
                "closing_order_id", sa.Integer(),
                sa.ForeignKey(
                    "system_paper_orders.id",
                    name="fk_system_paper_position_closing_order",
                ), nullable=True,
            ))


def downgrade():
    bind = op.get_bind()
    if _has_column(bind):
        with op.batch_alter_table("system_paper_positions") as batch:
            batch.drop_column("closing_order_id")
