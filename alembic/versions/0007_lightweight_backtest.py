"""add lightweight backtest engine tables

Revision ID: 0007
Revises: 0006
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABLES = [
    "backtest_runs",
    "backtest_trades",
    "backtest_equity_points",
    "backtest_pending_actions",
]


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
