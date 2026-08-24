"""add QMR point-in-time backtest research engine

Revision ID: 0029
Revises: 0028
"""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None
TABLES = ("qmr_parameter_sets", "qmr_backtest_runs", "qmr_backtest_cases",
          "qmr_backtest_results", "qmr_walk_forward_results")


def upgrade():
    bind = op.get_bind()
    for name in TABLES: Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES): Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
