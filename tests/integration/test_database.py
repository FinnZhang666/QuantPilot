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


def test_fresh_head_schema_matches_git_metadata(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh-0024.db'}"
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
        "created_at", "updated_at", "system_paper_position_id",
        "realized_return", "exit_reason", "fill_model_version",
        "data_quality", "source_snapshot_json",
    }
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "0033"


def test_qmr_exit_migration_round_trip(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "qmr-exit-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0031")
    engine = create_engine(url)
    names = {"qmr_money_flow_snapshots", "qmr_exit_evaluations", "qmr_exit_events"}
    for name in names:
        Base.metadata.tables[name].drop(engine, checkfirst=True)
    command.upgrade(config, "0032")
    assert names <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0031")
    assert not names.intersection(inspect(engine).get_table_names())
    command.upgrade(config, "0032")
    assert names <= set(inspect(engine).get_table_names())


def test_qmr_backtest_migration_round_trip(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "qmr-backtest-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0028")
    engine = create_engine(url)
    names = ("qmr_parameter_sets", "qmr_backtest_runs", "qmr_backtest_cases",
             "qmr_backtest_results", "qmr_walk_forward_results")
    for name in names: Base.metadata.tables[name].drop(engine, checkfirst=True)
    command.upgrade(config, "0029")
    assert set(names) <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0028")
    assert not (set(names) & set(inspect(engine).get_table_names()))
    command.upgrade(config, "0029")
    assert set(names) <= set(inspect(engine).get_table_names())


def test_buy_score_migration_round_trip(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "buy-score-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0027")
    engine = create_engine(url)
    names = ("buy_scores", "buy_rankings", "instrument_mappings")
    for name in names: Base.metadata.tables[name].drop(engine, checkfirst=True)
    command.upgrade(config, "0028")
    assert set(names) <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0027")
    assert not (set(names) & set(inspect(engine).get_table_names()))
    command.upgrade(config, "0028")
    assert "buy_scores" in inspect(engine).get_table_names()


def test_recovery_migration_round_trip(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "recovery-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0026")
    engine = create_engine(url)
    names = ("recovery_scores", "recovery_events")
    for name in names: Base.metadata.tables[name].drop(engine, checkfirst=True)
    command.upgrade(config, "0027")
    assert set(names) <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0026")
    assert not (set(names) & set(inspect(engine).get_table_names()))
    command.upgrade(config, "0027")
    assert "recovery_scores" in inspect(engine).get_table_names()


def test_qmr_migration_round_trip(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "qmr-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0025")
    engine = create_engine(url)
    names = ("qmr_candidates", "mispricing_scores", "quality_scores", "fundamental_snapshots")
    for name in names: Base.metadata.tables[name].drop(engine, checkfirst=True)
    command.upgrade(config, "0026")
    assert set(names) <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0025")
    assert not (set(names) & set(inspect(engine).get_table_names()))
    command.upgrade(config, "0026")
    assert "qmr_candidates" in inspect(engine).get_table_names()


def test_universe_migration_round_trip(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "universe-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0024")
    engine = create_engine(url)
    for name in ("universe_update_runs", "universe_memberships", "universe"):
        Base.metadata.tables[name].drop(engine, checkfirst=True)
    command.upgrade(config, "0025")
    assert {"universe", "universe_memberships", "universe_update_runs"} <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0024")
    assert "universe" not in inspect(engine).get_table_names()
    command.upgrade(config, "0025")
    assert "universe" in inspect(engine).get_table_names()


def test_telegram_runtime_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "telegram-runtime.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0022")
    engine = create_engine(url)
    expected = {
        "telegram_bot_profiles", "telegram_runtime_users", "telegram_admins",
        "telegram_feedback", "telegram_runtime_message_logs",
        "telegram_profile_sync_logs", "telegram_ai_invocations",
    }
    for name in expected:
        Base.metadata.tables[name].drop(engine, checkfirst=True)
    before = set(inspect(engine).get_table_names())
    command.upgrade(config, "0023")
    assert expected <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0022")
    assert set(inspect(engine).get_table_names()) == before
    command.upgrade(config, "0023")
    assert expected <= set(inspect(engine).get_table_names())


def test_single_bot_language_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "single-bot-language.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0023")
    engine = create_engine(url)
    command.upgrade(config, "0024")
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "0024"
    command.downgrade(config, "0023")
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == "0023"
    command.upgrade(config, "0024")
    assert "telegram_runtime_users" in inspect(engine).get_table_names()


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


def test_system_paper_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "system-paper-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0019")
    engine = create_engine(url)
    names = (
        "system_equity_snapshots", "system_paper_positions", "system_paper_fills",
        "system_paper_orders", "system_paper_accounts",
    )
    for name in names:
        Base.metadata.tables[name].drop(engine, checkfirst=True)
    before = set(inspect(engine).get_table_names())
    command.upgrade(config, "0020")
    assert set(names) <= set(inspect(engine).get_table_names())
    command.downgrade(config, "0019")
    assert set(inspect(engine).get_table_names()) == before
    command.upgrade(config, "0020")
    assert "system_paper_accounts" in inspect(engine).get_table_names()


def test_paper_exit_order_migration_upgrade_downgrade(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "paper-exit-migration.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert "closing_order_id" in {
        row["name"] for row in inspect(engine).get_columns("system_paper_positions")
    }
    command.downgrade(config, "0020")
    assert "closing_order_id" not in {
        row["name"] for row in inspect(engine).get_columns("system_paper_positions")
    }
    command.upgrade(config, "0021")
    assert "closing_order_id" in {
        row["name"] for row in inspect(engine).get_columns("system_paper_positions")
    }


def test_complete_paper_lifecycle_migration_round_trip(monkeypatch, tmp_path):
    url = "sqlite:///" + str(tmp_path / "complete-paper-lifecycle.db")
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    expected_tables = {
        "system_paper_audit_events", "system_paper_scheduler_jobs",
        "system_paper_runtime_locks",
    }
    assert expected_tables <= set(inspect(engine).get_table_names())
    assert "market_data_status" in {
        item["name"] for item in inspect(engine).get_columns("system_paper_positions")
    }
    command.downgrade(config, "0021")
    assert not (expected_tables & set(inspect(engine).get_table_names()))
    assert "market_data_status" not in {
        item["name"] for item in inspect(engine).get_columns("system_paper_positions")
    }
    command.upgrade(config, "head")
    assert expected_tables <= set(inspect(engine).get_table_names())
