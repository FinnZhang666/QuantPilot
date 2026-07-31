"""add user participation engine

Revision ID: 0016
Revises: 0015
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.tables["user_positions"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["user_positions"].drop(bind=op.get_bind(), checkfirst=True)
