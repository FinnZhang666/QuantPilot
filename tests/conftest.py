import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.database.base import Base


@pytest.fixture(autouse=True)
def clean_settings_cache(monkeypatch):
    for key in (
        "TRADING_MODE",
        "TELEGRAM_ENABLED",
        "TELEGRAM_RUNTIME_ENABLED",
        "TELEGRAM_RUNTIME_AUTOSTART",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "DATABASE_URL",
        "MOOMOO_LIVE_TRADING_ENABLED",
        "MOOMOO_ALLOW_ORDER_SUBMISSION",
        "MOOMOO_ENABLED",
        "DASHBOARD_ADMIN_TOKEN",
        "DASHBOARD_READONLY_PUBLIC",
        "AI_COMPANION_ENABLED",
        "AI_COMPANION_PROVIDER",
        "AI_COMPANION_MODEL",
        "AI_COMPANION_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    # Automated tests must never activate a real Telegram or Gemini transport,
    # even when the developer's ignored local .env enables production smoke tests.
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_RUNTIME_AUTOSTART", "false")
    monkeypatch.setenv("AI_COMPANION_ENABLED", "false")
    monkeypatch.setenv("AI_COMPANION_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
