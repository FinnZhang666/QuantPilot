"""add trade lifecycle foundation

Revision ID: 0015
Revises: 0014
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

TABLES = ("trade_plans", "trade_plan_transitions")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
