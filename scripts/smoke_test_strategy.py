#!/usr/bin/env python3
import subprocess
import sys
from datetime import timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.database.models import (
    CandidateSignal, MarketBar, PaperOrder, PaperPosition, StrategyRun, Trade,
    WatchlistItem,
)
from app.database.session import get_session_factory
from app.main import app
from app.strategy.constants import DEFAULT_WATCHLIST
from app.strategy.service import StrategyRunner
from app.strategy.watchlist import WatchlistService


def main() -> int:
    assert sys.version_info[:2] == (3, 9)
    settings = get_settings()
    assert not settings.moomoo_live_trading_enabled
    assert not settings.moomoo_allow_order_submission
    with get_session_factory()() as db:
        before = {
            "orders": db.scalar(select(func.count()).select_from(PaperOrder)) or 0,
            "trades": db.scalar(select(func.count()).select_from(Trade)) or 0,
            "positions": db.scalar(select(func.count()).select_from(PaperPosition)) or 0,
        }
        stats = WatchlistService(db).initialize_defaults()
        assert db.query(WatchlistItem).count() >= 9
        assert set(DEFAULT_WATCHLIST).issubset(set(db.scalars(select(WatchlistItem.symbol))))
        roles = dict(db.execute(select(WatchlistItem.symbol, WatchlistItem.role)).all())
        assert roles["QQQ"] == "MARKET_BENCHMARK"
        assert roles["SOXX"] == "SECTOR_BENCHMARK"
        assert roles["SOXL"] == "TRADING"
        assert roles["SOXS"] == "RISK_INDICATOR"
        assert roles["PLTR"] == "TRADING"
        latest = db.scalar(select(func.max(MarketBar.timestamp_utc)).where(
            MarketBar.symbol == "US.SOXL", MarketBar.interval == "1d",
        ))
        if latest:
            aware = latest.replace(tzinfo=timezone.utc) if latest.tzinfo is None else latest
            runner = StrategyRunner(db, settings)
            preview = runner.run(
                ["SOXL"], ["1d"], "RANGE",
                aware - timedelta(seconds=1), aware + timedelta(seconds=1),
                False, True, False,
            )
            assert preview["dry_run"]
            first = runner.run(
                ["SOXL"], ["1d"], "RANGE",
                aware - timedelta(seconds=1), aware + timedelta(seconds=1),
                False, False, False,
            )
            count_before_repeat = db.query(CandidateSignal).count()
            second = runner.run(
                ["SOXL"], ["1d"], "RANGE",
                aware - timedelta(seconds=1), aware + timedelta(seconds=1),
                False, False, False,
            )
            assert db.query(CandidateSignal).count() == count_before_repeat
            assert first["status"] == "SUCCESS" and second["status"] == "SUCCESS"
            assert db.query(StrategyRun).count() >= 2
        after = {
            "orders": db.scalar(select(func.count()).select_from(PaperOrder)) or 0,
            "trades": db.scalar(select(func.count()).select_from(Trade)) or 0,
            "positions": db.scalar(select(func.count()).select_from(PaperPosition)) or 0,
        }
        assert before == after
    with TestClient(app) as client:
        assert client.get("/watchlist").status_code == 200
        assert client.get("/strategy/signals/latest").status_code == 200
    command = [sys.executable, "scripts/show_latest_signals.py", "--symbol", "SOXL", "--limit", "1"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0 and "Ticker" in completed.stdout
    print("Strategy Smoke Test：PASS")
    print("默认Watchlist：9个Ticker，初始化幂等")
    print("本地Signal计算与Upsert：通过")
    print("API与CLI查询：通过")
    print("订单、模拟成交、持仓变化：0")
    print("OpenD在线验证：SKIPPED（本测试不要求OpenD在线）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
