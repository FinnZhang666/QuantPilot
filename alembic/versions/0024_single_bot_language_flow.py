"""add persistent single-Bot language selection

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


ALIASES = (
    ("trade_companion_ai_en", "trade_companion_ai"),
    ("trade_companion_zh", "quantpilot_ai"),
    ("trade_companion_en", "ai_stock_analyze"),
    ("quantpilot_ai_en", "jiaoyi_banlv"),
    ("stock_analysis_zh", "fenxi_gupiao"),
)


def upgrade():
    for old_alias, new_alias in ALIASES:
        op.execute(sa.text(
            "UPDATE telegram_bot_profiles SET alias = :new_alias "
            "WHERE alias = :old_alias AND NOT EXISTS ("
            "SELECT 1 FROM telegram_bot_profiles WHERE alias = :new_alias)"
        ).bindparams(old_alias=old_alias, new_alias=new_alias))


def downgrade():
    for old_alias, new_alias in reversed(ALIASES):
        op.execute(sa.text(
            "UPDATE telegram_bot_profiles SET alias = :old_alias "
            "WHERE alias = :new_alias AND NOT EXISTS ("
            "SELECT 1 FROM telegram_bot_profiles WHERE alias = :old_alias)"
        ).bindparams(old_alias=old_alias, new_alias=new_alias))
