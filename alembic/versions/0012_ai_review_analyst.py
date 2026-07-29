"""add AI review analyst

Revision ID: 0012
Revises: 0011
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.tables["ai_review_analyses"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["ai_review_analyses"].drop(bind=op.get_bind(), checkfirst=True)
