from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_database_migration(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"portfolios", "paper_orders", "trades", "system_events"}.issubset(tables)
