from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.database.base import Base


def test_database_migration(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"portfolios", "paper_orders", "trades", "system_events"}.issubset(tables)


def test_trade_lifecycle_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "lifecycle-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0014")
    engine = create_engine(url)
    # Legacy migrations reference current Base.metadata. Remove the Sprint 30
    # tables to faithfully model an existing database whose head is 0014.
    Base.metadata.tables["trade_plan_transitions"].drop(engine, checkfirst=True)
    Base.metadata.tables["trade_plans"].drop(engine, checkfirst=True)
    before = set(inspect(create_engine(url)).get_table_names())
    command.upgrade(config, "0015")
    upgraded = set(inspect(create_engine(url)).get_table_names())
    assert {"trade_plans", "trade_plan_transitions"} <= upgraded
    assert before <= upgraded
    command.downgrade(config, "0014")
    downgraded = set(inspect(create_engine(url)).get_table_names())
    assert "trade_plans" not in downgraded and "trade_plan_transitions" not in downgraded
    assert before == downgraded
    command.upgrade(config, "0015")
    assert "trade_plans" in inspect(create_engine(url)).get_table_names()
