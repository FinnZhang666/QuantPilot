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


def test_fresh_0019_schema_matches_git_metadata(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh-0019.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - {"alembic_version"} == set(Base.metadata.tables)
    assert {column["name"] for column in inspector.get_columns("trade_reviews")} >= {
        "review_key", "trade_plan_id", "user_position_id", "review_type",
        "result", "entry_price", "exit_price", "mfe", "mae",
        "holding_minutes", "target_hit", "stop_hit", "review_time",
        "created_at", "updated_at",
    }
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "0019"


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


def test_user_participation_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "participation-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0015")
    engine = create_engine(url)
    Base.metadata.tables["user_positions"].drop(engine, checkfirst=True)
    before = set(inspect(engine).get_table_names())
    command.upgrade(config, "0016")
    assert "user_positions" in inspect(engine).get_table_names()
    command.downgrade(config, "0015")
    assert set(inspect(engine).get_table_names()) == before
    command.upgrade(config, "0016")
    assert "user_positions" in inspect(engine).get_table_names()


def test_trade_review_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "trade-review-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0016")
    engine = create_engine(url)
    Base.metadata.tables["trade_reviews"].drop(engine, checkfirst=True)
    before = set(inspect(engine).get_table_names())
    command.upgrade(config, "0017")
    assert "trade_reviews" in inspect(engine).get_table_names()
    command.downgrade(config, "0016")
    assert set(inspect(engine).get_table_names()) == before
    command.upgrade(config, "0017")
    assert "trade_reviews" in inspect(engine).get_table_names()


def test_ai_companion_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "companion-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0017")
    engine = create_engine(url)
    Base.metadata.tables["companion_analyses"].drop(engine, checkfirst=True)
    before = set(inspect(engine).get_table_names())
    command.upgrade(config, "0018")
    assert "companion_analyses" in inspect(engine).get_table_names()
    command.downgrade(config, "0017")
    assert set(inspect(engine).get_table_names()) == before
    command.upgrade(config, "0018")
    assert "companion_analyses" in inspect(engine).get_table_names()


def test_portfolio_center_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "portfolio-center-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0018")
    engine = create_engine(url)
    for name in ("portfolio_watchlists", "portfolio_holdings", "investment_portfolios"):
        Base.metadata.tables[name].drop(engine, checkfirst=True)
    before = set(inspect(engine).get_table_names())
    command.upgrade(config, "0019")
    expected = {"investment_portfolios", "portfolio_holdings", "portfolio_watchlists"}
    assert expected <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0018")
    assert set(inspect(engine).get_table_names()) == before
    command.upgrade(config, "0019")
    assert "portfolio_holdings" in inspect(engine).get_table_names()
