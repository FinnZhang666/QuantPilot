"""add QMR market and sector context snapshots

Revision ID: 0033
Revises: 0032
"""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

TABLES = ("market_context_snapshots", "sector_context_snapshots")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
