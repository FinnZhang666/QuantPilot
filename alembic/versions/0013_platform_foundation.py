"""platform foundation and Telegram user research scopes

Revision ID: 0013
Revises: 0012
"""

from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.tables["telegram_user_symbols"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["telegram_user_symbols"].drop(bind=op.get_bind(), checkfirst=True)
