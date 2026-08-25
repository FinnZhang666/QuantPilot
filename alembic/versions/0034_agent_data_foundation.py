"""add Agent audit and canonical symbol registry

Revision ID: 0034
Revises: 0033
"""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

TABLES = ("symbol_registry", "agent_tool_audit")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
