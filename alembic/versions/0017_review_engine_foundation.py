"""add review engine foundation

Revision ID: 0017
Revises: 0016
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.tables["trade_reviews"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["trade_reviews"].drop(bind=op.get_bind(), checkfirst=True)
