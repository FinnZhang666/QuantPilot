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
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in {
            "moomoo_connection_checks",
            "instruments",
            "market_bars",
            "history_sync_jobs",
            "history_data_issues",
        }
    ]
    Base.metadata.create_all(bind=bind, tables=tables)


def downgrade():
    bind = op.get_bind()
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in {
            "moomoo_connection_checks",
            "instruments",
            "market_bars",
            "history_sync_jobs",
            "history_data_issues",
        }
    ]
    Base.metadata.drop_all(bind=bind, tables=tables)
