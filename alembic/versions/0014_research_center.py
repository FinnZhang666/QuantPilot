"""add research center

Revision ID: 0014
Revises: 0013
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

TABLES = (
    "research_workspaces", "research_timeline_events", "research_evidence",
    "research_notes", "research_attachments", "research_investigations",
)


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
