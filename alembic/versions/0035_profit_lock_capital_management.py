"""add profit lock and capital allocation ledger

Revision ID: 0035
Revises: 0034
"""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

TABLES = ("capital_management_states", "capital_transfers")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
