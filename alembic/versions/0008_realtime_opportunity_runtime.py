"""add realtime opportunity runtime

Revision ID: 0008
Revises: 0007
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TABLES = ["opportunities", "runtime_status"]


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
