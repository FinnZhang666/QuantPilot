"""add buy score engine

Revision ID: 0028
Revises: 0027
"""
from alembic import op
from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None
TABLES = ("buy_scores", "buy_rankings", "instrument_mappings")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
