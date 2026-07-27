#!/usr/bin/env python3
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.enums import TradingMode
from app.data.providers.moomoo import MoomooConnectionChecker
from app.database.init import DEFAULT_PORTFOLIOS
from app.database.models import HistorySyncJob, Instrument, MarketBar, Portfolio
from app.historical.factory import build_history_provider
from app.historical.instruments import InstrumentService
from app.database.session import get_session_factory
from app.notifications.telegram import TelegramNotificationProvider


def main() -> int:
    settings = get_settings()
    assert settings.trading_mode != TradingMode.LIVE
    with get_session_factory()() as db:
        db.execute(text("SELECT 1"))
        codes = set(db.scalars(select(Portfolio.code)))
        InstrumentService(db).initialize_defaults()
        assert db.query(Instrument).count() >= 13
        HistorySyncJob.__table__
        MarketBar.__table__
    assert set(DEFAULT_PORTFOLIOS).issubset(codes)
    TelegramNotificationProvider(settings)
    MoomooConnectionChecker(settings.moomoo_opend_host, settings.moomoo_opend_port)
    build_history_provider(settings)
    print("Smoke test: PASS")
    print("LIVE trading: BLOCKED")
    print("Moomoo：已初始化，但未自动连接或下载历史行情")
    print("历史行情模型、标的服务和索引：通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
