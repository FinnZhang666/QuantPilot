"""add versioned feature engine

Revision ID: 0005
Revises: 0004
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLES = [
    "feature_definitions",
    "feature_values",
    "feature_calculation_jobs",
    "feature_quality_issues",
]


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind)
