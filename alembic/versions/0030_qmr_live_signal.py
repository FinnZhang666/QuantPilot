"""add QMR live signal and validation loop

Revision ID: 0030
Revises: 0029
"""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None
TABLES = ("qmr_live_signals", "qmr_signal_performance",
          "qmr_signal_participations", "qmr_signal_deliveries")


def upgrade():
    bind = op.get_bind()
    for name in TABLES: Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES): Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
