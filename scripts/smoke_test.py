#!/usr/bin/env python3
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.enums import TradingMode
from app.data.providers.moomoo import MoomooConnectionChecker
from app.database.init import DEFAULT_PORTFOLIOS
from app.database.models import Portfolio
from app.database.session import get_session_factory
from app.notifications.telegram import TelegramNotificationProvider


def main() -> int:
    settings = get_settings()
    assert settings.trading_mode != TradingMode.LIVE
    with get_session_factory()() as db:
        db.execute(text("SELECT 1"))
        codes = set(db.scalars(select(Portfolio.code)))
    assert set(DEFAULT_PORTFOLIOS).issubset(codes)
    TelegramNotificationProvider(settings)
    MoomooConnectionChecker(settings.moomoo_opend_host, settings.moomoo_opend_port)
    print("Smoke test: PASS")
    print("LIVE trading: BLOCKED")
    print("Moomoo: initialized without automatic connection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
