"""add isolated system paper runtime ledger

Revision ID: 0020
Revises: 0019
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

TABLES = (
    "system_paper_accounts",
    "system_paper_orders",
    "system_paper_fills",
    "system_paper_positions",
    "system_equity_snapshots",
)


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
