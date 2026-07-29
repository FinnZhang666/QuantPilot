import argparse
from datetime import datetime, timezone
from decimal import Decimal

from app.backtest.service import BacktestService
from app.database.session import get_session_factory


def parse_time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def main():
    parser = argparse.ArgumentParser(description="运行轻量历史回测（不连接券商、不下单）")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--mode", default="SIGNAL_REPLAY", choices=["SIGNAL_REPLAY", "STRATEGY_RECOMPUTE"])
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--slippage-bps", default="0")
    parser.add_argument("--no-force-close", action="store_true")
    args = parser.parse_args()
    with get_session_factory()() as db:
        try:
            result = BacktestService(db).run(
                args.symbol, args.timeframe, parse_time(args.start), parse_time(args.end),
                args.mode, initial_cash=Decimal(args.initial_cash),
                slippage_bps=Decimal(args.slippage_bps),
                force_close_at_end=not args.no_force_close,
            )
        except (ValueError, RuntimeError) as exc:
            print("回测失败：%s" % exc)
            return 1
    print("回测完成")
    print("任务ID：%s" % result["run_id"])
    print("状态：%s" % result["status"])
    print("K线数量：%s" % result["bars_processed"])
    print("Signal数量：%s" % result["signals_processed"])
    print("完整交易：%s" % result["trades"])
    print("Benchmark：%s（%s）" % (result["benchmark_symbol"], result["benchmark_status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
