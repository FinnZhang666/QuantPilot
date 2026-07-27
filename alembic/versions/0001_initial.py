"""Initial safe paper-trading schema."""
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
