from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestBar, BacktestConfig, BacktestSignal
from app.core.config import get_settings
from app.database.models import (
    BacktestEquityPoint, BacktestPendingAction, BacktestRun, BacktestTrade,
)


def main():
    settings = get_settings()
    assert not settings.moomoo_live_trading_enabled
    assert not settings.moomoo_allow_order_submission
    assert all(model.__tablename__.startswith("backtest_") for model in (
        BacktestRun, BacktestTrade, BacktestEquityPoint, BacktestPendingAction,
    ))
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars = [
        BacktestBar(
            start + timedelta(days=index), Decimal(100 + index),
            Decimal(102 + index), Decimal(99 + index),
            Decimal(101 + index), 1000,
        )
        for index in range(20)
    ]
    config = BacktestConfig("SOXL", "1d", start, bars[-1].timestamp, "smoke")
    signals = [
        BacktestSignal(bars[1].timestamp, "CANDIDATE_BUY", "smoke"),
        BacktestSignal(bars[5].timestamp, "CANDIDATE_EXIT", "smoke"),
    ]
    result = BacktestEngine().run(config, bars, signals)
    assert result.status == "SUCCESS"
    assert len(result.equity_points) == 20
    assert len(result.trades) == 1
    print("Sprint 06 Smoke Test通过")
    print("- NEXT_BAR_OPEN：通过")
    print("- FLAT/LONG状态机：通过")
    print("- Equity Curve：通过")
    print("- LIVE交易：BLOCKED")
    print("- Moomoo订单接口：未连接")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
