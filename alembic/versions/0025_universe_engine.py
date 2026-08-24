"""add configurable universe engine

Revision ID: 0025
Revises: 0024
"""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

TABLES = ("universe", "universe_memberships", "universe_update_runs")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
