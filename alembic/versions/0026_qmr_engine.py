"""add quality and mispricing engine

Revision ID: 0026
Revises: 0025
"""
from alembic import op
from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None
TABLES = ("fundamental_snapshots", "quality_scores", "mispricing_scores", "qmr_candidates")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
