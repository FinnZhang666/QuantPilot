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
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "DATABASE_URL",
        "MOOMOO_LIVE_TRADING_ENABLED",
        "MOOMOO_ALLOW_ORDER_SUBMISSION",
        "MOOMOO_ENABLED",
        "DASHBOARD_ADMIN_TOKEN",
        "DASHBOARD_READONLY_PUBLIC",
    ):
        monkeypatch.delenv(key, raising=False)
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
