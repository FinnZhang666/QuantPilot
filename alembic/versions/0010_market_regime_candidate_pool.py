"""add market regime and candidate pool

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

from app.database.base import Base
from app.database.models import *  # noqa: F401,F403

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.tables["market_regimes"].create(bind=bind, checkfirst=True)
    Base.metadata.tables["candidate_pool_runs"].create(bind=bind, checkfirst=True)
    Base.metadata.tables["candidate_pool_entries"].create(bind=bind, checkfirst=True)
    columns = {item["name"] for item in sa.inspect(bind).get_columns("opportunities")}
    if "candidate_pool_entry_id" not in columns:
        op.execute(
            "ALTER TABLE opportunities ADD COLUMN candidate_pool_entry_id "
            "INTEGER REFERENCES candidate_pool_entries(id)"
        )
    if "market_regime_id" not in columns:
        op.execute(
            "ALTER TABLE opportunities ADD COLUMN market_regime_id "
            "INTEGER REFERENCES market_regimes(id)"
        )


def downgrade():
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("opportunities")}
    with op.batch_alter_table("opportunities", recreate="always") as batch:
        if "market_regime_id" in columns:
            batch.drop_column("market_regime_id")
        if "candidate_pool_entry_id" in columns:
            batch.drop_column("candidate_pool_entry_id")
    Base.metadata.tables["candidate_pool_entries"].drop(bind=bind, checkfirst=True)
    Base.metadata.tables["candidate_pool_runs"].drop(bind=bind, checkfirst=True)
    Base.metadata.tables["market_regimes"].drop(bind=bind, checkfirst=True)
