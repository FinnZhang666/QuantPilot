"""add portfolio center foundation

Revision ID: 0019
Revises: 0018
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


TABLES = ("investment_portfolios", "portfolio_holdings", "portfolio_watchlists")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
