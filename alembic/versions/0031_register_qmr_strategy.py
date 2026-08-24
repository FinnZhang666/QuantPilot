"""register QMR in the existing strategy catalog

Revision ID: 0031
Revises: 0030
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

CODE = "quality_mispricing_recovery"


def upgrade():
    connection = op.get_bind()
    exists = connection.execute(sa.text(
        "SELECT id FROM strategies WHERE code = :code"
    ), {"code": CODE}).scalar()
    if exists is None:
        config = {"short_name": "QMR", "strategy_type": ["REVERSAL", "MEAN_REPAIR", "EVENT_REPAIR"],
                  "market": "US", "universe": ["QQQ", "SPY"],
                  "modules": ["Universe", "Quality", "Mispricing", "Recovery", "Buy Score",
                              "Backtest", "Live Signals", "Cases"],
                  "operational_status": "RESEARCH"}
        connection.execute(sa.text(
            "INSERT INTO strategies "
            "(code, name, version, description, is_enabled, config_json, created_at, updated_at) "
            "VALUES (:code, :name, :version, :description, 1, :config, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"code": CODE, "name": "优质错杀修复", "version": "QMR-v1.0",
            "description": (
                "在优质公司因市场恐慌、行业联动、短期事件或估值压缩出现异常大跌后，"
                "先判断公司与行业长期逻辑是否仍然成立，再等待卖压衰竭、资金回流和趋势修复，"
                "在反转早期产生介入信号。"
            ),
            "config": json.dumps(config, ensure_ascii=False)})


def downgrade():
    op.get_bind().execute(sa.text(
        "DELETE FROM strategies WHERE code = :code"
    ), {"code": CODE})
