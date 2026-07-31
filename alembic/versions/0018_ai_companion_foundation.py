"""add AI companion foundation

Revision ID: 0018
Revises: 0017
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.tables["companion_analyses"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["companion_analyses"].drop(bind=op.get_bind(), checkfirst=True)
