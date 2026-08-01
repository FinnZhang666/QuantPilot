"""add the unified Telegram product runtime

Revision ID: 0023
Revises: 0022
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


TABLES = (
    "telegram_bot_profiles",
    "telegram_runtime_users",
    "telegram_admins",
    "telegram_feedback",
    "telegram_runtime_message_logs",
    "telegram_profile_sync_logs",
    "telegram_ai_invocations",
)


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
