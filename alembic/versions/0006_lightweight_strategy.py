"""add lightweight strategy signals and automated watchlist

Revision ID: 0006
Revises: 0005
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TABLES = [
    "watchlist_items",
    "watchlist_timeframes",
    "strategy_parameter_sets",
    "candidate_signals",
    "strategy_runs",
]


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
