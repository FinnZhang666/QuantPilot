"""add opportunity review engine

Revision ID: 0011
Revises: 0010
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.tables["opportunity_reviews"].create(bind=bind, checkfirst=True)
    Base.metadata.tables["review_statistics"].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    Base.metadata.tables["review_statistics"].drop(bind=bind, checkfirst=True)
    Base.metadata.tables["opportunity_reviews"].drop(bind=bind, checkfirst=True)
