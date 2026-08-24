"""add QMR exit risk and money-flow audit records

Revision ID: 0032
Revises: 0031
"""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

TABLES = (
    "qmr_money_flow_snapshots",
    "qmr_exit_evaluations",
    "qmr_exit_events",
)


def upgrade():
    bind = op.get_bind()
    # The legacy 0001 migration creates current metadata tables on a fresh
    # database. checkfirst keeps both fresh installs and incremental upgrades
    # safe until that historical migration can be retired in a dedicated task.
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
