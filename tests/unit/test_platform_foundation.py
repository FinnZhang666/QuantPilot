import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backup import BackupService
from app.candidate_pool.user_scope import TelegramUserScopeService
from app.config.settings import Settings
from app.core.security import mask_secret, sanitize_mapping, sanitize_text
from app.database.models import TelegramUserSymbol
from app.notifications.telegram_commands import TelegramCommandPoller, TelegramCommandService
from app.platform.environment import validate_environment
from app.platform.health import health_report, runtime_diagnostics
from app.version import version_info


def test_settings_platform_defaults():
    value = Settings()
    assert value.log_directory == "logs"
    assert value.backup_daily_retention == 7
    assert value.backup_weekly_retention == 4


@pytest.mark.parametrize("value", ["secret", "12345678", "123456789"])
def test_secret_mask_never_returns_original(value):
    assert mask_secret(value) != value


def test_secret_mapping_nested():
    value = sanitize_mapping({"telegram_token": "123456789", "nested": {"password": "abcdefghi"}})
    assert value["telegram_token"] != "123456789"
    assert value["nested"]["password"] != "abcdefghi"


def test_secret_text_redacts_telegram_token():
    assert "123456789:" not in sanitize_text("bad 123456789:AAxxxxxxxxxxxxxxxx")


def test_environment_validation_has_required_checks(db):
    value = validate_environment(Settings(), db)
    assert {"database", "python", "telegram", "dashboard", "disk"} <= {
        row["name"] for row in value["checks"]
    }


def test_environment_missing_optional_is_warning(db):
    value = validate_environment(Settings(telegram_enabled=False, dashboard_admin_token=""), db)
    assert value["status"] in {"PASS", "WARNING"}


def test_version_center_fields(db):
    assert {"product", "version", "sprint", "commit", "migration", "python"} <= set(version_info(db))
    assert version_info(db)["product"] == "Trade Companion"


def test_health_report(db):
    value = health_report(db, Settings(database_url=str(db.bind.url)))
    assert value["database"]["status"] == "OK"
    assert value["live_trading"] == "blocked"


def test_runtime_diagnostics_counts(db):
    value = runtime_diagnostics(db, Settings(database_url=str(db.bind.url)))
    assert value["pending_opportunities"] == 0
    assert value["pending_reviews"] == 0
    assert value["pending_ai"] == 0


def backup_settings(tmp_path, db):
    return Settings(
        database_url=str(db.bind.url), backup_directory=str(tmp_path / "backups"),
        backup_daily_retention=2, backup_weekly_retention=1,
    )


def test_backup_create_and_verify(tmp_path, db, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = BackupService(backup_settings(tmp_path, db))
    value = service.create()
    assert value["valid"] and Path(value["path"]).exists()
    assert "database/quantpilot.db" in value["files"]
    with zipfile.ZipFile(value["path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["product"] == "Trade Companion"


def test_backup_list(tmp_path, db, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = BackupService(backup_settings(tmp_path, db))
    service.create()
    assert len(service.list()) == 1


def test_backup_invalid_type(tmp_path, db):
    with pytest.raises(ValueError):
        BackupService(backup_settings(tmp_path, db)).create("cloud")


def test_backup_missing_verify(tmp_path, db):
    with pytest.raises(FileNotFoundError):
        BackupService(backup_settings(tmp_path, db)).verify()


def test_backup_verify_streams_archive_in_bounded_chunks(tmp_path, db, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = BackupService(backup_settings(tmp_path, db))
    value = service.create()

    def reject_unbounded_read(self):
        raise AssertionError("backup verification must not load the whole archive")

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_read)
    assert service.verify(value["path"])["valid"] is True


def test_telegram_poller_survives_unexpected_iteration_error(monkeypatch):
    poller = TelegramCommandPoller(Settings(telegram_enabled=True, telegram_bot_token="test-token"))
    states = []

    def unexpected_failure(*args, **kwargs):
        raise RuntimeError("unexpected database-adjacent failure")

    def capture_state(status, error=None, success=False):
        states.append((status, error, success))
        poller.stop_event.set()

    monkeypatch.setattr("app.notifications.telegram_commands.httpx.get", unexpected_failure)
    monkeypatch.setattr(poller, "_state", capture_state)
    poller._loop()

    assert states == [("DEGRADED", "RuntimeError", False)]


def test_user_scope_normalizes_and_is_idempotent(db):
    service = TelegramUserScopeService(db)
    assert service.add("1", " us.nvda ") == "NVDA"
    assert service.add("1", "NVDA") == "NVDA"
    assert service.symbols("1") == ["NVDA"]


def test_user_scope_isolated(db):
    service = TelegramUserScopeService(db)
    service.add("1", "NVDA")
    service.add("2", "AAPL")
    assert service.symbols("1") == ["NVDA"]
    assert service.symbols("2") == ["AAPL"]


def test_user_scope_soft_remove(db):
    service = TelegramUserScopeService(db)
    service.add("1", "NVDA")
    assert service.remove("1", "NVDA")
    assert service.symbols("1") == []
    assert db.query(TelegramUserSymbol).count() == 1


@pytest.mark.parametrize("value", ["", "A B", "$BAD", "A" * 20])
def test_user_scope_rejects_invalid(value):
    with pytest.raises(ValueError):
        TelegramUserScopeService.normalize(value)


def test_telegram_watch_commands_isolate_users(db):
    service = TelegramCommandService(db, Settings(telegram_admin_ids="1,2"))
    assert service.handle("1", "/watch add NVDA")[0]
    assert service.handle("2", "/watch add AAPL")[0]
    assert "NVDA" in service.handle("1", "/watchlist")[1]
    assert "AAPL" not in service.handle("1", "/watchlist")[1]


def test_telegram_non_admin_cannot_manage_scope(db):
    service = TelegramCommandService(db, Settings(telegram_admin_ids="1"))
    assert service.handle("2", "/watch add NVDA")[0] is False


def test_telegram_admin_username_case_insensitive(db):
    service = TelegramCommandService(
        db, Settings(telegram_admin_usernames="adhd360,Kevinchou8"),
    )
    assert service.handle("100", "/watch add NVDA", username="ADHD360")[0]
    assert service.handle("200", "/watch add AAPL", username="@kevinchou8")[0]
    assert TelegramUserScopeService(db).symbols("100") == ["NVDA"]
    assert TelegramUserScopeService(db).symbols("200") == ["AAPL"]


def test_platform_config_safe_dict_excludes_secrets():
    value = Settings(
        telegram_bot_token="123456789:AAxxxxxxxxxxxxxxxx",
        dashboard_admin_token="dashboard-secret",
    ).safe_dict()
    text = json.dumps(value)
    assert "AAxxxxxxxx" not in text and "dashboard-secret" not in text
