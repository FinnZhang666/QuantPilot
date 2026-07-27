"""Add safe Moomoo capability check history."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "moomoo_connection_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opend_reachable", sa.Boolean(), nullable=False),
        sa.Column("opend_logged_in", sa.Boolean(), nullable=False),
        sa.Column("sdk_version", sa.String(32), nullable=False),
        sa.Column("opend_version", sa.String(32), nullable=False),
        sa.Column("quote_capabilities_json", sa.JSON(), nullable=False),
        sa.Column("paper_account_found", sa.Boolean(), nullable=False),
        sa.Column("live_account_found", sa.Boolean(), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("status_code", sa.String(32), nullable=False),
        sa.Column("status_message_zh", sa.String(255), nullable=False),
    )


def downgrade():
    op.drop_table("moomoo_connection_checks")
