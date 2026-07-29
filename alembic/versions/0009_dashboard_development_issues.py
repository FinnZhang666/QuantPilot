"""add dashboard development issues

Revision ID: 0009
Revises: 0008
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.tables["development_issues"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["development_issues"].drop(bind=op.get_bind(), checkfirst=True)
